// The menu bar panel: small and quiet, in the manner of the system's own menu bar menus. The card
// (its newest photo, what's new, where it goes) with one inline action; a few rows on the glass;
// everything secondary behind ⋯.

import SwiftUI

let brand = Color(red: 0.0, green: 0.56, blue: 0.56)

// MARK: building blocks

/// A round icon like Control Center's: grey, or filled with the accent when it needs you.
struct RoundIcon: View {
    let symbol: String
    var active = false
    var body: some View {
        Image(systemName: symbol)
            .font(.system(size: 10.5, weight: .semibold))
            .foregroundStyle(active ? Color.white : Color.primary.opacity(0.85))
            .frame(width: 22, height: 22)
            .background(Circle().fill(active ? AnyShapeStyle(brand) : AnyShapeStyle(.fill.tertiary)))
    }
}

/// A menu row: a highlight only under the pointer.
struct MenuRowStyle: ButtonStyle {
    @State private var hover = false
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .padding(.horizontal, 7).padding(.vertical, 3)
            .frame(maxWidth: .infinity, alignment: .leading)
            .contentShape(Rectangle())
            .background(RoundedRectangle(cornerRadius: 6, style: .continuous)
                .fill(Color.primary.opacity(configuration.isPressed ? 0.14 : hover ? 0.08 : 0)))
            .onHover { hover = $0 }
            .padding(.horizontal, 5)
    }
}

struct MenuRow: View {
    let symbol: String
    let title: String
    var detail: String? = nil
    var active = false
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(spacing: 9) {
                RoundIcon(symbol: symbol, active: active)
                Text(title).font(.system(size: 13)).foregroundStyle(.primary).lineLimit(1)
                Spacer(minLength: 6)
                if let detail { Text(detail).font(.system(size: 12)).foregroundStyle(.secondary).lineLimit(1) }
            }
        }
        .buttonStyle(MenuRowStyle())
    }
}

struct Rule: View {
    var body: some View { Divider().padding(.horizontal, 12).padding(.vertical, 5) }
}

/// The card's newest photo in a circle; a ring around it shows progress.
struct CardPicture: View {
    let photo: NSImage?
    var symbol = "sdcard"
    var progress: Double? = nil
    var spinning = false
    @State private var turn = false

    var ringed: Bool { progress != nil || spinning }

    var body: some View {
        ZStack {
            if ringed {
                Circle().stroke(.fill.tertiary, lineWidth: 2.5)
                Circle().trim(from: 0, to: spinning ? 0.25 : max(0.02, min(progress ?? 0, 1)))
                    .stroke(brand, style: StrokeStyle(lineWidth: 2.5, lineCap: .round))
                    .rotationEffect(.degrees(spinning ? (turn ? 270 : -90) : -90))
                    .animation(spinning ? .linear(duration: 1).repeatForever(autoreverses: false) : .smooth, value: turn)
                    .animation(.smooth, value: progress)
            }
            SwiftUI.Group {
                if let photo {
                    Image(nsImage: photo).resizable().aspectRatio(contentMode: .fill)
                } else {
                    Image(systemName: symbol).font(.system(size: 15, weight: .medium)).foregroundStyle(.secondary)
                        .frame(maxWidth: .infinity, maxHeight: .infinity).background(.fill.tertiary)
                }
            }
            .frame(width: ringed ? 33 : 40, height: ringed ? 33 : 40)
            .clipShape(Circle())
        }
        .frame(width: 40, height: 40)
        .onAppear { turn = true }
    }
}

extension View {
    /// The one inline action: a small capsule, Liquid Glass on macOS 26.
    @ViewBuilder func mainAction() -> some View {
        #if compiler(>=6.2)
        if #available(macOS 26.0, *) {
            self.buttonStyle(.glassProminent).buttonBorderShape(.capsule).tint(brand).controlSize(.regular)
        } else {
            self.buttonStyle(.borderedProminent).buttonBorderShape(.capsule).tint(brand).controlSize(.regular)
        }
        #else
        self.buttonStyle(.borderedProminent).buttonBorderShape(.capsule).tint(brand).controlSize(.regular)
        #endif
    }
}

func image(fromDataURI uri: String?) -> NSImage? {
    guard let uri, let comma = uri.firstIndex(of: ","),
          let data = Data(base64Encoded: String(uri[uri.index(after: comma)...])) else { return nil }
    return NSImage(data: data)
}

/// "Soumya_T7 › Sony Backup" for /Volumes/Soumya_T7/Photos/Sony Backup.
func placeName(_ path: String) -> String {
    let parts = path.split(separator: "/").map(String.init)
    let drive = parts.count > 1 && parts[0] == "Volumes" ? parts[1] : "This Mac"
    return parts.last.map { $0 == drive ? drive : "\(drive) › \($0)" } ?? drive
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
                Text(failure).font(.system(size: 12)).foregroundStyle(.red).padding(.horizontal, 12).padding(.bottom, 8)
            } else if !engine.ready {
                HStack(spacing: 8) { ProgressView().controlSize(.small); Text("Starting…").foregroundStyle(.secondary) }
                    .font(.system(size: 12)).padding(.horizontal, 12).padding(.bottom, 10)
            } else {
                hero
                if let note {
                    Text(note.text).font(.system(size: 11.5))
                        .foregroundStyle(note.bad ? Color.red : Color.secondary)
                        .padding(.horizontal, 12).padding(.bottom, 6).padding(.top, -2)
                }
                cardActions
                Rule()
                MenuRow(symbol: "square.stack.3d.up.fill", title: "HDR Merge", detail: hdrDetail,
                        active: s.hdr_new.int > 0) { openHDR() }
                if let latest = s.update.latest.string {
                    MenuRow(symbol: "arrow.down", title: "Update to \(latest)", detail: "Copy line", active: true) {
                        NSPasteboard.general.clearContents()
                        NSPasteboard.general.setString(s.update.line.str, forType: .string)
                        note = ("Install line copied. Paste it into Terminal.", false)
                    }
                }
            }
        }
        .padding(.top, 2).padding(.bottom, 6)
        .frame(width: 290)
        .animation(.smooth(duration: 0.2), value: s.job.json)
        .onAppear { loginOn = System.opensAtLogin; Task { await engine.refresh() } }
    }

    // MARK: header

    var header: some View {
        HStack {
            Text("ShotLoft").font(.system(size: 13, weight: .semibold))
            Spacer()
            Menu {
                Button("Open Backup Folder") { if let d = s.dest.string { System.showInFinder(d) } }
                    .disabled(!s.dest_exists.bool)
                Toggle("Open at Login", isOn: Binding(get: { loginOn },
                                                      set: { System.setOpensAtLogin($0); loginOn = System.opensAtLogin }))
                Divider()
                Text("ShotLoft \(s.version.str)")
                Button("Quit ShotLoft") { NSApp.terminate(nil) }
            } label: {
                Image(systemName: "ellipsis").font(.system(size: 12, weight: .semibold)).foregroundStyle(.secondary)
                    .frame(width: 22, height: 18).contentShape(Rectangle())
            }
            .menuStyle(.borderlessButton).menuIndicator(.hidden).fixedSize()
        }
        .padding(.horizontal, 12).padding(.top, 7).padding(.bottom, 7)
    }

    // MARK: the card

    var card: J { s.cards[0] }
    var cardName: String {
        let n = s.cards.array.count
        return card.name.str + (n > 1 ? " +\(n - 1)" : "")
    }

    @ViewBuilder var hero: some View {
        let job = s.job, r = job.result, p = job.progress
        let kind = job.kind.str, st = job.state.str
        let photo = image(fromDataURI: card.photo.string)
        let idle = st != "running"

        if !s.dest.exists {
            heroRow(CardPicture(photo: nil, symbol: "folder"), "Choose a backup folder", "Where photos and videos go",
                    action: HeroAction(title: "Choose…", run: pickBackup), showDest: false)
        } else if !s.dest_drive_connected.bool {
            heroRow(CardPicture(photo: nil, symbol: "externaldrive"), "\(placeName(s.dest.str)) isn't connected",
                    "Plug in your backup drive", tone: .red)
        } else if s.cards.array.isEmpty {
            heroRow(CardPicture(photo: nil), "No memory card", "Put one in to back it up")
        } else if !job.exists || (kind == "plan" && st == "running") {
            heroRow(CardPicture(photo: photo, progress: p.exists ? p.done.double / max(p.total.double, 1) : nil, spinning: !p.exists),
                    cardName, p.exists ? "Reading \(p.done.int) of \(p.total.int) files…" : "Checking what's new…")
        } else if st == "error" {
            heroRow(CardPicture(photo: photo), cardName, job.error.str, tone: .red,
                    action: HeroAction(title: "Retry", run: retry))
        } else if st == "running" && kind == "import" {
            let f = p.done.double / max(p.total.double, 1)
            heroRow(CardPicture(photo: photo, progress: f), cardName,
                    p.exists ? "Copying \(p.files_done.int) of \(p.files_total.int)\(timeLeft(p))" : "Starting…",
                    trailing: "\(Int(f * 100))%", showDest: true)
        } else if st == "running" && kind == "verify" {
            heroRow(CardPicture(photo: photo, progress: p.exists ? p.done.double / max(p.total.double, 1) : nil, spinning: !p.exists),
                    cardName, "Checking byte by byte…")
        } else if kind == "plan" {
            if r.new_files.int == 0 {
                heroRow(CardPicture(photo: photo), cardName, "Everything is backed up", tone: .green)
            } else if !r.enough_space.bool {
                heroRow(CardPicture(photo: photo), cardName, "Needs \(human(r.needed_bytes.double)) more space", tone: .red)
            } else {
                heroRow(CardPicture(photo: photo), cardName,
                        "\(newCounts(r.new_photos.int, r.new_videos.int, r.new_xml.int)) · \(human(r.needed_bytes.double))",
                        action: idle ? HeroAction(title: "Back Up", run: backUp) : nil)
            }
        } else if kind == "import" {
            let errs = r.errors.array.count
            heroRow(CardPicture(photo: photo), cardName,
                    errs > 0 ? "\(plural(errs, "file")) couldn't be copied" : "Backed up \(counts(r.photos.int, r.videos.int, r.xml.int))",
                    tone: errs > 0 ? .red : .green)
        } else if kind == "verify" {
            let bad = r.cards.array.reduce(0) { $0 + $1.missing.array.count + $1.different.array.count }
            heroRow(CardPicture(photo: photo), cardName, bad > 0 ? "\(plural(bad, "file")) not backed up yet" : "Safe to format",
                    tone: bad > 0 ? .red : .green)
        }
    }

    enum Tone { case normal, green, red }

    struct HeroAction {
        let title: String
        let run: () -> Void
    }

    func heroRow(_ picture: CardPicture, _ title: String, _ subtitle: String, tone: Tone = .normal,
                 action: HeroAction? = nil, trailing: String? = nil, showDest: Bool = true) -> some View {
        HStack(alignment: .center, spacing: 10) {
            picture
            VStack(alignment: .leading, spacing: 1) {
                Text(title).font(.system(size: 13, weight: .semibold)).lineLimit(1)
                Text(subtitle).font(.system(size: 11.5)).lineLimit(1)
                    .foregroundStyle(tone == .green ? AnyShapeStyle(Color.green) : tone == .red ? AnyShapeStyle(Color.red) : AnyShapeStyle(.secondary))
                if showDest && s.dest.exists { destination }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .layoutPriority(1)
            if let action {
                Button(action.title, action: action.run).mainAction().fixedSize()
            } else if let trailing {
                Text(trailing).font(.system(size: 12, weight: .medium)).monospacedDigit().foregroundStyle(.secondary)
            }
        }
        .padding(.horizontal, 12).padding(.bottom, 9)
    }

    /// Where the backup goes, chosen each time: the recent folders and "Choose Folder…".
    var destination: some View {
        Menu {
            ForEach(s.recent_dests.strings, id: \.self) { path in
                Button { useBackup(path) } label: {
                    if path == s.dest.str { Label(placeName(path), systemImage: "checkmark") } else { Text(placeName(path)) }
                }
            }
            Divider()
            Button("Choose Folder…") { pickBackup() }
        } label: {
            Text("To \(placeName(s.dest.str)) \(Image(systemName: "chevron.up.chevron.down"))")
                .font(.system(size: 11.5)).foregroundStyle(.tertiary).lineLimit(1)
        }
        .menuStyle(.borderlessButton).menuIndicator(.hidden)
        .disabled(s.job.state.str == "running")
        .help("Choose where this backup goes")
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
                MenuRow(symbol: "checkmark.shield.fill", title: "Check Before Formatting") {
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

    var hdrDetail: String? {
        let j = s.hdr_job
        if j.state.str == "running" { return j.kind.str == "merge" ? "Merging…" : nil }
        let n = s.hdr_new.int
        return n > 0 ? "\(n) new" : nil
    }

    // MARK: actions

    func say(_ error: String?) async {
        withAnimation { note = error.map { ($0, true) } }
    }

    func backUp() { Task { await say(engine.act("/api/import")) } }

    func retry() { Task { await engine.act("/api/reset"); model.replan() } }

    func useBackup(_ path: String) {
        guard path != s.dest.str else { return }
        Task { await say(engine.act("/api/dest", ["path": path])); model.replan() }
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
