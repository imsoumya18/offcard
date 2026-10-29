// The ShotLoft engine (the Python app, bundled as a helper) and the app's view of its state.
//
// The menu bar app starts the engine with `--serve --agent`, reads its URL and per-launch token,
// and talks to the same local JSON API the Windows and Linux page uses. The engine watches for
// cards by itself (agent mode) and exits when this app does.

import Foundation
import SwiftUI

/// A read-only view of JSON from the engine: `state.job.result.new_files.int`.
@dynamicMemberLookup
struct J {
    let value: Any?
    init(_ value: Any?) { self.value = value is NSNull ? nil : value }

    subscript(dynamicMember key: String) -> J { J((value as? [String: Any])?[key]) }
    subscript(index: Int) -> J {
        guard let a = value as? [Any], a.indices.contains(index) else { return J(nil) }
        return J(a[index])
    }
    var exists: Bool { value != nil }
    var string: String? { value as? String }
    var str: String { string ?? "" }
    var int: Int { (value as? NSNumber)?.intValue ?? 0 }
    var double: Double { (value as? NSNumber)?.doubleValue ?? 0 }
    var bool: Bool { (value as? NSNumber)?.boolValue ?? false }
    var array: [J] { (value as? [Any])?.map { J($0) } ?? [] }
    var strings: [String] { (value as? [Any])?.compactMap { $0 as? String } ?? [] }
    /// Compact JSON text, to compare two values (such as which cards a check was made for).
    var json: String {
        guard let v = value, JSONSerialization.isValidJSONObject([v]),
              let d = try? JSONSerialization.data(withJSONObject: [v], options: [.sortedKeys]) else { return "null" }
        return String(decoding: d, as: UTF8.self)
    }
}

struct EngineError: LocalizedError {
    let message: String
    var errorDescription: String? { message }
}

@MainActor
final class Engine: ObservableObject {
    @Published private(set) var state = J(nil)
    @Published private(set) var ready = false
    @Published private(set) var failure: String?

    private var process: Process?
    private var base: URL?
    private var token = ""
    private var timer: Timer?

    var running: Bool {
        state.job.state.string == "running" || state.hdr_job.state.string == "running"
    }

    // MARK: starting and stopping

    func start() {
        let urlFile = FileManager.default.temporaryDirectory
            .appendingPathComponent("shotloft-\(ProcessInfo.processInfo.processIdentifier).json")
        try? FileManager.default.removeItem(at: urlFile)

        let p = Process()
        let env = ProcessInfo.processInfo.environment
        if let dev = env["SHOTLOFT_ENGINE"], !dev.isEmpty {   // development: "python3 /path/to/shotloft.py"
            let parts = dev.split(separator: " ").map(String.init)
            p.executableURL = URL(fileURLWithPath: "/usr/bin/env")
            p.arguments = parts + ["--serve", "--agent"]
        } else {
            p.executableURL = Bundle.main.resourceURL!.appendingPathComponent("engine/ShotLoftEngine")
            p.arguments = ["--serve", "--agent"]
        }
        var childEnv = env
        childEnv["SHOTLOFT_URL_FILE"] = urlFile.path
        p.environment = childEnv
        p.standardOutput = FileHandle.nullDevice
        p.standardError = FileHandle.standardError
        do {
            try p.run()
        } catch {
            failure = "ShotLoft's engine couldn't start: \(error.localizedDescription)"
            return
        }
        process = p

        Task {
            for _ in 0..<600 {   // up to a minute: the first launch unpacks the engine
                if let d = try? Data(contentsOf: urlFile), !d.isEmpty,
                   let info = try? JSONSerialization.jsonObject(with: d) as? [String: Any],
                   let url = info["url"] as? String, let tok = info["token"] as? String,
                   var parts = URLComponents(string: url) {
                    parts.path = ""
                    parts.query = nil
                    base = parts.url
                    token = tok
                    try? FileManager.default.removeItem(at: urlFile)
                    ready = true
                    await refresh()
                    schedule()
                    return
                }
                if !p.isRunning {
                    failure = "ShotLoft's engine stopped while starting (code \(p.terminationStatus))."
                    return
                }
                try? await Task.sleep(nanoseconds: 100_000_000)
            }
            failure = "ShotLoft's engine didn't start in time."
        }
    }

    func stop() {
        timer?.invalidate()
        process?.terminate()
    }

    private func schedule() {
        timer?.invalidate()
        let interval = running ? 0.5 : 1.5
        timer = Timer.scheduledTimer(withTimeInterval: interval, repeats: false) { [weak self] _ in
            Task { @MainActor in
                await self?.refresh()
                self?.schedule()
            }
        }
    }

    // MARK: the API

    func refresh() async {
        if let s = try? await call("/api/state") { state = s }
    }

    /// GET when body is nil, POST otherwise. Throws the engine's own message on failure.
    @discardableResult
    func call(_ path: String, _ body: [String: Any]? = nil) async throws -> J {
        guard let base else { throw EngineError(message: "ShotLoft is still starting.") }
        var req = URLRequest(url: base.appendingPathComponent(path))
        req.setValue(token, forHTTPHeaderField: "X-Token")
        req.timeoutInterval = 30
        if let body {
            req.httpMethod = "POST"
            req.setValue("application/json", forHTTPHeaderField: "Content-Type")
            req.httpBody = try JSONSerialization.data(withJSONObject: body)
        }
        let (data, resp) = try await URLSession.shared.data(for: req)
        let json = J(try? JSONSerialization.jsonObject(with: data))
        if (resp as? HTTPURLResponse)?.statusCode != 200 {
            throw EngineError(message: json.error.string ?? "Something went wrong.")
        }
        return json
    }

    /// Run an action, refresh straight after, and return its error message if it failed.
    @discardableResult
    func act(_ path: String, _ body: [String: Any] = [:]) async -> String? {
        do {
            try await call(path, body)
            await refresh()
            schedule()
            return nil
        } catch {
            await refresh()
            return error.localizedDescription
        }
    }
}

// MARK: small formatters, like the page's

func human(_ n: Double) -> String {
    ByteCountFormatter.string(fromByteCount: Int64(n), countStyle: .binary)
        .replacingOccurrences(of: "bytes", with: "B")
}

func plural(_ n: Int, _ word: String) -> String { "\(n.formatted()) \(word)\(n == 1 ? "" : "s")" }

func counts(_ p: Int, _ v: Int, _ x: Int = 0) -> String {
    let parts = [p > 0 ? plural(p, "photo") : nil, v > 0 ? plural(v, "video") : nil,
                 x > 0 ? plural(x, "video info file") : nil].compactMap { $0 }
    if parts.isEmpty { return "nothing" }
    return parts.count == 1 ? parts[0] : parts.dropLast().joined(separator: ", ") + " and " + parts.last!
}

/// "18 new photos and 2 videos"
func newCounts(_ p: Int, _ v: Int, _ x: Int = 0) -> String {
    let text = counts(p, v, x)
    guard let space = text.firstIndex(of: " ") else { return text }
    return text[..<space] + " new" + text[space...]
}

func duration(_ s: Double) -> String {
    let s = Int(s.rounded())
    return s < 60 ? "\(s)s" : "\(s / 60)m \(String(format: "%02d", s % 60))s"
}
