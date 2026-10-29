// The menu bar panel, in the manner of the system's own menu bar menus (Wi-Fi, Bluetooth, Control
// Center): rows straight on the glass, hairline dividers between groups, round icons, a highlight
// only under the pointer. The card's newest photo is the picture at the top.

import SwiftUI

let brand = Color(red: 0.0, green: 0.56, blue: 0.56)

// MARK: building blocks

/// A round icon like Control Center's: grey, or filled with the accent when it needs you.
struct RoundIcon: View {
    let symbol: String
    var active = false
    var tint: Color = brand
    var body: some View {
        Image(systemName: symbol)
            .font(.system(size: 12, weight: .semibold))
            .foregroundStyle(active ? Color.white : Color.primary)
            .frame(width: 26, height: 26)
            .background(Circle().fill(active ? AnyShapeStyle(tint) : AnyShapeStyle(.fill.tertiary)))
    }
}

/// A menu row: highlights under the pointer, like a menu item.
struct MenuRowStyle: ButtonStyle {
    @State private var hover = false
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .padding(.horizontal, 8).padding(.vertical, 4)
            .frame(maxWidth: .infinity, alignment: .leading)
            .contentShape(Rectangle())
            .background(RoundedRectangle(cornerRadius: 7, style: .continuous)
                .fill(Color.primary.opacity(configuration.isPressed ? 0.16 : hover ? 0.09 : 0)))
            .onHover { hover = $0 }
            .padding(.horizontal, 6)
    }
}

struct MenuRow: View {
    let symbol: String?
    let title: String
    var detail: String? = nil
    var active = false
    var tint: Color = brand
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(spacing: 10) {
                if let symbol { RoundIcon(symbol: symbol, active: active, tint: tint) }
                Text(title).font(.system(size: 13)).foregroundStyle(.primary).lineLimit(1)
                Spacer(minLength: 8)
                if let detail {
                    Text(detail).font(.system(size: 12)).foregroundStyle(.secondary).lineLimit(1)
                }
            }
            .frame(minHeight: symbol == nil ? 20 : 28)
        }
        .buttonStyle(MenuRowStyle())
    }
}

struct SectionLabel: View {
    let text: String
    init(_ text: String) { self.text = text }
    var body: some View {
        Text(text).font(.system(size: 11, weight: .semibold)).foregroundStyle(.secondary)
            .padding(.horizontal, 14).padding(.top, 2).padding(.bottom, 3)
    }
}

struct Rule: View {
    var body: some View { Divider().padding(.horizontal, 14).padding(.vertical, 6) }
}

/// The card's newest photo in a circle, with a small card badge; a ring around it shows progress.
struct CardPicture: View {
    let photo: NSImage?
    var symbol = "sdcard.fill"
    var progress: Double? = nil
    var spinning = false
    @State private var turn = false

    var ringed: Bool { progress != nil || spinning }

    var body: some View {
        ZStack(alignment: .bottomTrailing) {
            ZStack {
                if ringed {
                    Circle().stroke(.fill.tertiary, lineWidth: 3)
                    Circle().trim(from: 0, to: spinning ? 0.25 : max(0.02, min(progress ?? 0, 1)))
                        .stroke(brand, style: StrokeStyle(lineWidth: 3, lineCap: .round))
                        .rotationEffect(.degrees(spinning ? (turn ? 270 : -90) : -90))
                        .animation(spinning ? .linear(duration: 1).repeatForever(autoreverses: false) : .smooth, value: turn)
                        .animation(.smooth, value: progress)
                }
                SwiftUI.Group {
                    if let photo {
                        Image(nsImage: photo).resizable().aspectRatio(contentMode: .fill)
                    } else {
                        Image(systemName: symbol).font(.system(size: 20, weight: .medium)).foregroundStyle(.secondary)
                            .frame(maxWidth: .infinity, maxHeight: .infinity).background(.fill.tertiary)
                    }
                }
                .frame(width: ringed ? 44 : 54, height: ringed ? 44 : 54)
                .clipShape(Circle())
            }
            .frame(width: 54, height: 54)
            if photo != nil {
                Image(systemName: "sdcard.fill").font(.system(size: 9, weight: .semibold)).foregroundStyle(.secondary)
                    .frame(width: 19, height: 19)
                    .background(Circle().fill(.background))
                    .offset(x: 2, y: 2)
            }
        }
        .onAppear { turn = true }
    }
}

extension View {
    /// The one main action: a capsule, Liquid Glass on macOS 26.
    @ViewBuilder func mainAction() -> some View {
        #if compiler(>=6.2)
        if #available(macOS 26.0, *) {
            self.buttonStyle(.glassProminent).buttonBorderShape(.capsule).tint(brand).controlSize(.large)
        } else {
            self.buttonStyle(.borderedProminent).buttonBorderShape(.capsule).tint(brand).controlSize(.large)
        }
        #else
        self.buttonStyle(.borderedProminent).buttonBorderShape(.capsule).tint(brand).controlSize(.large)
        #endif
    }
}

func image(fromDataURI uri: String?) -> NSImage? {
    guard let uri, let comma = uri.firstIndex(of: ","),
          let data = Data(base64Encoded: String(uri[uri.index(after: comma)...])) else { return nil }
    return NSImage(data: data)
}

// MARK: the panel

struct PanelView: View {
    @EnvironmentObject var engine: Engine
    @EnvironmentObject var model: AppModel
    @Environment(\.openWindow) private var openWindow
    @Environment(\.dismiss) private var dismiss
    @State private var note: (text: String, bad: Bool)?
    @State private var loginOn = System.opensAtLogin

    var s: J { engine.state }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            header
            if let failure = engine.failure {
                Text(failure).font(.system(size: 12)).foregroundStyle(.red).padding(.horizontal, 14).padding(.vertical, 8)
            } else if !engine.ready {
                HStack(spacing: 8) { ProgressView().controlSize(.small); Text("Starting…").foregroundStyle(.secondary) }
                    .padding(.horizontal, 14).padding(.vertical, 18)
            } else {
                hero
                if let note {
                    Label(note.text, systemImage: note.bad ? "exclamationmark.circle.fill" : "checkmark.circle.fill")
                        .font(.system(size: 12)).foregroundStyle(note.bad ? Color.red : Color.secondary)
                        .padding(.horizontal, 14).padding(.bottom, 8)
                }
                cardActions
                drive
                Rule()
                MenuRow(symbol: "square.stack.3d.up.fill", title: "HDR Merge", detail: hdrDetail,
                        active: s.hdr_new.int > 0) { openHDR() }
                if let latest = s.update.latest.string {
                    MenuRow(symbol: "arrow.down", title: "Update to \(latest)", detail: "Copy install line", active: true) {
                        NSPasteboard.general.clearContents()
                        NSPasteboard.general.setString(s.update.line.str, forType: .string)
                        note = ("Install line copied. Paste it into Terminal.", false)
                    }
                }
            }
            Rule()
            MenuRow(symbol: nil, title: "Open Backup Folder") {
                if let d = s.dest.string, s.dest_exists.bool { System.showInFinder(d); dismiss() }
            }
            MenuRow(symbol: nil, title: "Quit ShotLoft") { NSApp.terminate(nil) }
        }
        .padding(.top, 4).padding(.bottom, 7)
        .frame(width: 320)
        .animation(.smooth(duration: 0.22), value: s.job.json)
        .onAppear { loginOn = System.opensAtLogin; Task { await engine.refresh() } }
    }

    // MARK: header

    var header: some View {
        HStack {
            Text("ShotLoft").font(.system(size: 13, weight: .semibold))
            Spacer()
            Menu {
                Toggle("Open at Login", isOn: Binding(get: { loginOn },
                                                      set: { System.setOpensAtLogin($0); loginOn = System.opensAtLogin }))
                Button("Change Backup Folder…") { pickBackup() }
                Divider()
                Text("ShotLoft \(s.version.str)")
            } label: {
                Image(systemName: "ellipsis").font(.system(size: 13, weight: .semibold)).foregroundStyle(.secondary)
                    .frame(width: 24, height: 20).contentShape(Rectangle())
            }
            .menuStyle(.borderlessButton).menuIndicator(.hidden).fixedSize()
        }
        .padding(.horizontal, 14).padding(.top, 6).padding(.bottom, 8)
    }

    // MARK: the card

    var card: J { s.cards[0] }
    var cardName: String {
        let n = s.cards.array.count
        return card.name.str + (n > 1 ? " and \(n - 1) more" : "")
    }

    @ViewBuilder var hero: some View {
        let job = s.job, r = job.result, p = job.progress
        let kind = job.kind.str, st = job.state.str
        let photo = image(fromDataURI: card.photo.string)
        VStack(alignment: .leading, spacing: 12) {
            if !s.dest.exists {
                heroLine(CardPicture(photo: nil, symbol: "folder.fill"), "Choose a backup folder", "Where your photos and videos go")
                Button { pickBackup() } label: { Text("Choose Folder…").frame(maxWidth: .infinity) }.mainAction()
            } else if !s.dest_drive_connected.bool {
                heroLine(CardPicture(photo: nil, symbol: "externaldrive.fill"), "\(driveName) isn't connected",
                         "Plug in your backup drive", tone: .red)
            } else if s.cards.array.isEmpty {
                heroLine(CardPicture(photo: nil, symbol: "sdcard"), "No memory card", "Put one in and ShotLoft checks it")
            } else if !job.exists || (kind == "plan" && st == "running") {
                heroLine(CardPicture(photo: photo, progress: p.exists ? p.done.double / max(p.total.double, 1) : nil, spinning: !p.exists),
                         cardName, p.exists ? "Reading \(p.done.int) of \(p.total.int) files on the card…" : "Checking what's new…")
            } else if st == "error" {
                heroLine(CardPicture(photo: photo), cardName, job.error.str, tone: .red)
                Button { Task { await engine.act("/api/reset"); model.replan() } } label: {
                    Text("Try Again").frame(maxWidth: .infinity) }.mainAction()
            } else if st == "running" && kind == "import" {
                let f = p.done.double / max(p.total.double, 1)
                heroLine(CardPicture(photo: photo, progress: f), cardName,
                         p.exists ? "Copying \(p.files_done.int) of \(p.files_total.int) files\(timeLeft(p))" : "Starting…")
            } else if st == "running" && kind == "verify" {
                heroLine(CardPicture(photo: photo, progress: p.exists ? p.done.double / max(p.total.double, 1) : nil, spinning: !p.exists),
                         cardName, "Checking every file, byte by byte…")
            } else if kind == "plan" {
                if r.new_files.int == 0 {
                    heroLine(CardPicture(photo: photo), cardName, "Everything is backed up", tone: .green)
                } else if !r.enough_space.bool {
                    heroLine(CardPicture(photo: photo), cardName, "Not enough space for \(human(r.needed_bytes.double))", tone: .red)
                } else {
                    heroLine(CardPicture(photo: photo), cardName,
                             "\(newCounts(r.new_photos.int, r.new_videos.int, r.new_xml.int)) · \(human(r.needed_bytes.double))")
                    Button { Task { await say(engine.act("/api/import")) } } label: {
                        Text("Back Up").frame(maxWidth: .infinity) }.mainAction()
                }
            } else if kind == "import" {
                let errs = r.errors.array.count
                heroLine(CardPicture(photo: photo), cardName,
                         errs > 0 ? "\(plural(errs, "file")) couldn't be copied"
                            : "Backed up \(counts(r.photos.int, r.videos.int, r.xml.int))\(r.seconds.double >= 1 ? " in " + duration(r.seconds.double) : "")",
                         tone: errs > 0 ? .red : .green)
            } else if kind == "verify" {
                let bad = r.cards.array.reduce(0) { $0 + $1.missing.array.count + $1.different.array.count }
                heroLine(CardPicture(photo: photo), cardName,
                         bad > 0 ? "\(plural(bad, "file")) not backed up yet. Don't format." : "Safe to format in your camera",
                         tone: bad > 0 ? .red : .green)
            }
        }
        .padding(.horizontal, 14).padding(.bottom, 12)
    }

    enum Tone { case normal, green, red }

    func heroLine(_ picture: CardPicture, _ title: String, _ subtitle: String, tone: Tone = .normal) -> some View {
        HStack(spacing: 12) {
            picture
            VStack(alignment: .leading, spacing: 2) {
                Text(title).font(.system(size: 14, weight: .semibold)).lineLimit(1)
                Text(subtitle).font(.system(size: 12)).lineLimit(2)
                    .foregroundStyle(tone == .green ? AnyShapeStyle(Color.green) : tone == .red ? AnyShapeStyle(Color.red) : AnyShapeStyle(.secondary))
                    .contentTransition(.opacity)
            }
            Spacer(minLength: 0)
        }
    }

    func timeLeft(_ p: J) -> String {
        let done = p.done.double, total = p.total.double, t = p.elapsed.double
        guard t > 2, done > 0, done < total else { return "" }
        return " · \(duration((total - done) / (done / t))) left"
    }

    // MARK: after a backup

    @ViewBuilder var cardActions: some View {
        let job = s.job, kind = job.kind.str
        let finished = job.state.str == "done" && !s.cards.array.isEmpty &&
            ((kind == "plan" && job.result.new_files.int == 0) || kind == "import" || kind == "verify")
        if finished {
            Rule()
            if kind != "verify" {
                MenuRow(symbol: "checkmark.shield.fill", title: "Check It's Safe to Format", detail: "Byte by byte") {
                    Task { await say(engine.act("/api/verify")) }
                }
            }
            if kind == "import", job.result.raw_jpg_pairs.int > 0 {
                MenuRow(symbol: "trash.fill", title: "Move Extra JPGs to \(s.trash_name.str)",
                        detail: "\(job.result.raw_jpg_pairs.int)") { Task { await trash() } }
            }
            MenuRow(symbol: "eject.fill", title: "Eject \(card.name.str)") { Task { await eject() } }
        }
    }

    // MARK: drive and tools

    var driveName: String {
        let d = s.dest_drive.str
        return d.isEmpty ? "This Mac" : (d as NSString).lastPathComponent
    }

    @ViewBuilder var drive: some View {
        if s.dest.exists {
            Rule()
            SectionLabel(s.cards.array.isEmpty ? "Backup drive" : "Also plugged in")
            MenuRow(symbol: s.dest_drive.exists ? "externaldrive.fill" : "internaldrive.fill", title: driveName,
                    detail: s.dest_drive_connected.bool
                        ? (s.job.kind.str == "import" && s.job.state.str == "running" ? "Writing…"
                           : s.free_bytes.exists ? "\(human(s.free_bytes.double)) free" : "Backup drive")
                        : "Not connected") {
                if let d = s.dest.string, s.dest_exists.bool { System.showInFinder(d); dismiss() }
            }
        }
    }

    var hdrDetail: String? {
        let j = s.hdr_job
        if j.state.str == "running" { return j.kind.str == "merge" ? "Merging…" : "Looking…" }
        let n = s.hdr_new.int
        return n > 0 ? plural(n, "new set") : nil
    }

    // MARK: actions

    func say(_ error: String?) async {
        withAnimation { note = error.map { ($0, true) } }
    }

    func pickBackup() {
        guard let path = System.chooseFolder("Choose where ShotLoft backs up your photos and videos", startingAt: s.dest.string) else { return }
        Task { await say(engine.act("/api/dest", ["path": path])); model.replan() }
    }

    func eject() async {
        do {
            let r = try await engine.call("/api/eject", [:])
            if let bad = r.results.array.first(where: { !$0.ejected.bool }) {
                note = ("Couldn't eject \((bad.card.str as NSString).lastPathComponent). Eject it in Finder.", true)
            } else {
                note = ("Ejected. You can take the card out.", false)
            }
        } catch { note = (error.localizedDescription, true) }
        await engine.refresh()
    }

    func trash() async {
        do {
            let r = try await engine.call("/api/trash", [:])
            note = ("Moved \(plural(r.moved.int, "JPG")) to the \(s.trash_name.str).", false)
        } catch { note = (error.localizedDescription, true) }
        await engine.refresh()
    }

    func openHDR() {
        dismiss()
        openWindow(id: "hdr")
        NSApp.activate(ignoringOtherApps: true)
    }
}
