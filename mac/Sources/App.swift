// ShotLoft for the Mac: a menu bar app (SwiftUI) in front of the ShotLoft engine.
//
//   ShotLoft              the menu bar app
//   ShotLoft --version    print the version (the installer uses it)
//   ShotLoft --check      start the engine, ask it for its state, print PASS (tests)

import Combine
import SwiftUI

@main
enum Main {
    static func main() {
        let args = CommandLine.arguments
        if args.contains("--version") {
            print("shotloft \(Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "?")")
            exit(0)
        }
        if args.contains("--check") { exit(Check.run()) }
        ShotLoftApp.main()
    }
}

struct ShotLoftApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) var delegate
    @StateObject private var model = AppModel.shared

    var body: some Scene {
        MenuBarExtra {
            PanelView().environmentObject(model.engine).environmentObject(model)
        } label: {
            Image(nsImage: model.icon)
        }
        .menuBarExtraStyle(.window)

        Window("HDR Merge", id: "hdr") {
            HDRView().environmentObject(model.engine)
        }
        .defaultSize(width: 760, height: 660)
        .windowResizability(.contentMinSize)
    }
}

final class AppDelegate: NSObject, NSApplicationDelegate {
    func applicationDidFinishLaunching(_ note: Notification) {
        NSApp.setActivationPolicy(.accessory)   // a menu bar app: no Dock icon
        if ProcessInfo.processInfo.environment["SHOTLOFT_DEV"] == nil {  // development builds skip these
            System.askForNotifications()
            System.setUpLoginItemOnce()
        }
    }

    func applicationWillTerminate(_ note: Notification) {
        MainActor.assumeIsolated { AppModel.shared.engine.stop() }
    }
}

/// What the app does on its own as the engine's state changes: checks a card when it goes in,
/// tells the user about new files, and keeps the menu bar icon current.
@MainActor
final class AppModel: ObservableObject {
    static let shared = AppModel()

    let engine = Engine()
    @Published private(set) var icon = System.menuBarIcon()

    private var lastKey = ""
    private var notified = ""
    private var hdrLooked = ""   // the folder, and the backup after which, HDR sets were last counted
    private var lastBackup = ""
    private var iconState = ""
    private var watch: AnyCancellable?

    private init() {
        watch = engine.$state.sink { [weak self] s in self?.update(s) }
        engine.start()
    }

    /// Check again (after the backup folder changes, or Try Again).
    func replan() { lastKey = "" }

    /// The cards and backup folder a check is for, the way the engine reports it (plan_for).
    private func key(_ s: J) -> String {
        let cards = s.cards.array.map(\.path.str).sorted()
        return J([cards, s.dest.value ?? NSNull()]).json
    }

    private func update(_ s: J) {
        guard s.exists else { return }
        let job = s.job, k = key(s)
        let cardsIn = !s.cards.array.isEmpty
        let planned = job.kind.str == "plan" && job.state.str == "done" && s.plan_for.json == k

        // A new card (or folder): check what's new, unless the engine already has.
        if !cardsIn { lastKey = "" }
        if cardsIn, s.dest.exists, s.dest_drive_connected.bool, job.state.str != "running", k != lastKey {
            lastKey = k
            if !planned { Task { try? await engine.call("/api/plan", [:]) } }
        }

        // Count the HDR folder's unmerged sets (for "3 new sets"): at start, and after each backup.
        let afterBackup = job.kind.str == "import" && job.state.str == "done" ? "\(job.id.double)" : lastBackup
        lastBackup = afterBackup
        let hdrKey = s.hdr_folder.str + "|" + afterBackup
        if s.hdr_folder.exists, s.hdr_folder_exists.bool, s.hdr_job.state.str != "running", hdrKey != hdrLooked {
            hdrLooked = hdrKey
            Task { try? await engine.call("/api/hdr/scan", [:]) }
        }

        // New files: say so once per card.
        if planned, job.result.new_files.int > 0, k != notified {
            notified = k
            let r = job.result
            let name = s.cards[0].name.str
            System.notify(name.isEmpty ? "Memory card" : name,
                          "\(counts(r.new_photos.int, r.new_videos.int, r.new_xml.int)) to back up. Click ShotLoft in the menu bar.")
        }
        if !cardsIn { notified = "" }

        // The icon: a ring while copying, a dot while a card has new files.
        var state = "idle"
        var progress: Double?
        if job.kind.str == "import", job.state.str == "running" {
            progress = job.progress.done.double / max(job.progress.total.double, 1)
            state = "copy-\(Int((progress ?? 0) * 20))"
        } else if planned, job.result.new_files.int > 0 {
            state = "new"
        }
        if state != iconState {
            iconState = state
            icon = System.menuBarIcon(dot: state == "new", progress: progress)
        }
    }
}

/// `--check`: the bundled engine starts and answers. No window, for CI and the installer.
enum Check {
    static func run() -> Int32 {
        let file = FileManager.default.temporaryDirectory.appendingPathComponent("shotloft-check-\(getpid()).json")
        let p = Process()
        p.executableURL = Bundle.main.resourceURL!.appendingPathComponent("engine/ShotLoftEngine")
        p.arguments = ["--serve"]
        var env = ProcessInfo.processInfo.environment
        env["SHOTLOFT_URL_FILE"] = file.path
        env["SHOTLOFT_NO_UPDATE_CHECK"] = "1"
        p.environment = env
        p.standardOutput = FileHandle.nullDevice
        do { try p.run() } catch { print("FAIL: engine didn't start: \(error)"); return 1 }
        defer { p.terminate() }
        for _ in 0..<600 {
            if let d = try? Data(contentsOf: file), let info = try? JSONSerialization.jsonObject(with: d) as? [String: Any],
               let url = info["url"] as? String, let token = info["token"] as? String, var parts = URLComponents(string: url) {
                parts.path = "/api/state"; parts.query = nil
                var req = URLRequest(url: parts.url!)
                req.setValue(token, forHTTPHeaderField: "X-Token")
                let done = DispatchSemaphore(value: 0)
                var version: String?
                URLSession.shared.dataTask(with: req) { data, _, _ in
                    if let data, let s = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
                        version = s["version"] as? String
                    }
                    done.signal()
                }.resume()
                done.wait()
                try? FileManager.default.removeItem(at: file)
                let mine = Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String
                guard let version else { print("FAIL: the engine didn't answer"); return 1 }
                guard mine == nil || mine == version else { print("FAIL: app \(mine!) but engine \(version)"); return 1 }
                print("PASS")
                return 0
            }
            if !p.isRunning { print("FAIL: engine stopped (code \(p.terminationStatus))"); return 1 }
            usleep(100_000)
        }
        print("FAIL: engine didn't start in time")
        return 1
    }
}
