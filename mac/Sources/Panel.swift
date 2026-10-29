// The menu bar panel, built like the system's own (Wi-Fi, Bluetooth, Control Center): rows straight
// on the glass under small section headings, one round icon and one text column throughout, the
// system accent colour only, and one plain button for the one thing to do next.
//
// Type: 13 for rows, 11 for the line under a row, 11 semibold for headings. Colour: the accent,
// green only for "safe", red only for problems; everything else is the system's greys.

import SwiftUI

let brand = Color.accentColor

enum Metrics {
    static let width: CGFloat = 300
    static let inset: CGFloat = 14          // the panel's edge to a row's icon
    static let icon: CGFloat = 26
    static let gap: CGFloat = 10            // icon to text
    static var text: CGFloat { inset + icon + gap }   // where every row's text starts
}

// MARK: building blocks

/// A round icon like Control Center's: grey, or filled with the accent when it needs you.
struct RoundIcon: View {
    let symbol: String
    var active = false
    var tint: Color? = nil
    var body: some View {
        Image(systemName: symbol)
            .font(.system(size: 12, weight: .medium))
            .foregroundStyle(active || tint != nil ? Color.white : Color.primary)
            .frame(width: Metrics.icon, height: Metrics.icon)
            .background(Circle().fill(tint.map { AnyShapeStyle($0) }
                ?? (active ? AnyShapeStyle(brand) : AnyShapeStyle(Color.primary.opacity(0.1)))))
    }
}

/// A row's hover highlight, as in the system's menus.
struct MenuRowStyle: ButtonStyle {
    @State private var hover = false
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .frame(maxWidth: .infinity, alignment: .leading)
            .contentShape(Rectangle())
            .background(RoundedRectangle(cornerRadius: 7, style: .continuous)
                .fill(Color.primary.opacity(configuration.isPressed ? 0.14 : hover ? 0.08 : 0))
                .padding(.horizontal, 5))
            .onHover { hover = $0 }
    }
}

/// An icon, a title, and an optional line under it.
struct RowContent<Trailing: View>: View {
    let symbol: String
    var active = false
    var tint: Color? = nil
    let title: String
    var subtitle: String? = nil
    var subtitleColor: Color? = nil
    @ViewBuilder var trailing: Trailing

    var body: some View {
        HStack(spacing: Metrics.gap) {
            RoundIcon(symbol: symbol, active: active, tint: tint)
            VStack(alignment: .leading, spacing: 1) {
                Text(title).font(.system(size: 13)).foregroundStyle(.primary).lineLimit(1)
                if let subtitle {
                    Text(subtitle).font(.system(size: 11))
                        .foregroundStyle(subtitleColor.map { AnyShapeStyle($0) } ?? AnyShapeStyle(.secondary))
                        .lineLimit(2).fixedSize(horizontal: false, vertical: true)
                }
            }
            Spacer(minLength: 6)
            trailing
        }
        .padding(.horizontal, Metrics.inset)
        .frame(minHeight: 38)
    }
}

extension RowContent where Trailing == EmptyView {
    init(symbol: String, active: Bool = false, tint: Color? = nil, title: String,
         subtitle: String? = nil, subtitleColor: Color? = nil) {
        self.init(symbol: symbol, active: active, tint: tint, title: title, subtitle: subtitle,
                  subtitleColor: subtitleColor) { EmptyView() }
    }
}

/// A clickable row.
struct MenuRow: View {
    let symbol: String
    let title: String
    var detail: String? = nil
    var active = false
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            RowContent(symbol: symbol, active: active, title: title) {
                if let detail { Text(detail).font(.system(size: 11)).foregroundStyle(.secondary) }
            }
        }
        .buttonStyle(MenuRowStyle())
    }
}

struct SectionHeading: View {
    let title: String
    var body: some View {
        Text(title).font(.system(size: 11, weight: .semibold)).foregroundStyle(.secondary)
            .padding(.horizontal, Metrics.inset).padding(.top, 6).padding(.bottom, 1)
    }
}

struct Rule: View {
    var body: some View { Divider().padding(.horizontal, Metrics.inset).padding(.vertical, 5) }
}

/// The card's newest shots: small rounded previews in the text column.
struct PhotoStrip: View {
    let photos: [NSImage]
    static let tile: CGFloat = 44

    var body: some View {
        HStack(spacing: 5) {
            ForEach(Array(photos.prefix(5).enumerated()), id: \.offset) { _, photo in
                Image(nsImage: photo).resizable().aspectRatio(contentMode: .fill)
                    .frame(width: Self.tile, height: Self.tile)
                    .clipShape(RoundedRectangle(cornerRadius: 6, style: .continuous))
                    .overlay(RoundedRectangle(cornerRadius: 6, style: .continuous)
                        .strokeBorder(Color.primary.opacity(0.1), lineWidth: 0.5))
            }
        }
        .padding(.leading, Metrics.text).padding(.bottom, 4)
        .accessibilityHidden(true)
    }
}

extension View {
    /// The one main action: Liquid Glass on macOS 26, a filled button before; the system accent.
    @ViewBuilder func mainAction(large: Bool = false) -> some View {
        let size: ControlSize = large ? .large : .regular
        #if compiler(>=6.2)
        if #available(macOS 26.0, *) {
            self.buttonStyle(.glassProminent).controlSize(size)
        } else {
            self.buttonStyle(.borderedProminent).controlSize(size)
        }
        #else
        self.buttonStyle(.borderedProminent).controlSize(size)
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
    let (drive, folder) = place(path)
    return folder.map { "\(drive) › \($0)" } ?? drive
}

/// The drive, and the folder on it (nil when the folder is the drive itself).
func place(_ path: String) -> (drive: String, folder: String?) {
    let parts = path.split(separator: "/").map(String.init)
    let drive = parts.count > 1 && parts[0] == "Volumes" ? parts[1] : "This Mac"
    guard let last = parts.last, last != drive else { return (drive, nil) }
    return (drive, last)
}

/// The folders a backup will create inside the backup folder, like Finder's list view. Folders
/// that already exist are joined into one line ("2026 › 10. October"); new ones are marked where
/// they start, and each shows how many files go into it. Long trips show the first few days, then
/// "and N more days".
struct FolderPreview: View {
    let tree: J
    static let dayLimit = 3

    struct Row: Identifiable {
        let id: Int
        let indent: Int
        let name: String
        let new: Bool
        let files: Int
        let leaf: Bool
        let label: Bool          // where a new branch starts
    }

    var rows: (shown: [Row], moreDays: Int) {
        var rows: [Row] = [], days = 0
        // level: 1 year, 2 month, 3 day, 4 Photos/Videos
        func walk(_ start: J, _ level: Int, _ indent: Int, _ parentNew: Bool) {
            if days >= Self.dayLimit && level <= 3 {      // past the limit: count, don't show
                days += dayCount(start, level)
                return
            }
            var node = start, last = level, names = [start.name.str]
            while !node.new.bool, node.children.array.count == 1, let only = node.children.array.first, !only.new.bool {
                node = only
                last += 1
                names.append(only.name.str)
            }
            if level <= 3 && last >= 3 { days += 1 }
            let children = node.children.array
            rows.append(Row(id: rows.count, indent: indent, name: names.joined(separator: " › "), new: node.new.bool,
                            files: node.files.int, leaf: children.isEmpty, label: !parentNew))
            children.forEach { walk($0, last + 1, indent + 1, node.new.bool) }
        }
        tree.children.array.forEach { walk($0, 1, 0, false) }   // the backup folder itself is the row above
        return (rows, max(0, days - Self.dayLimit))
    }

    func dayCount(_ node: J, _ level: Int) -> Int {
        level >= 3 ? 1 : node.children.array.reduce(0) { $0 + dayCount($1, level + 1) }
    }

    var body: some View {
        let (shown, moreDays) = rows
        VStack(alignment: .leading, spacing: 0) {
            ForEach(shown) { row in
                HStack(spacing: 5) {
                    Image(systemName: "folder.fill")
                        .font(.system(size: 11))
                        .foregroundStyle(row.new ? AnyShapeStyle(brand) : AnyShapeStyle(.tertiary))
                    Text(row.name).font(.system(size: 11))
                        .foregroundStyle(row.new ? .primary : .secondary)
                        .lineLimit(1).truncationMode(.middle)
                    if row.label && row.new {
                        Text("new").font(.system(size: 11)).foregroundStyle(brand)
                    }
                    Spacer(minLength: 6)
                    if row.files > 0 {
                        Text(plural(row.files, "file")).font(.system(size: 11)).monospacedDigit()
                            .foregroundStyle(.secondary)
                    }
                }
                .padding(.leading, CGFloat(row.indent) * 14)
                .frame(height: 18)
            }
            if moreDays > 0 {
                Text("and \(plural(moreDays, "more day"))")
                    .font(.system(size: 11)).foregroundStyle(.tertiary)
                    .padding(.leading, 30).frame(height: 18)
            }
        }
        .padding(.leading, Metrics.text).padding(.trailing, Metrics.inset).padding(.bottom, 2)
        .accessibilityElement(children: .combine)
        .accessibilityLabel("Folders this backup creates")
    }
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
            Text("ShotLoft").font(.system(size: 13, weight: .bold))
                .padding(.horizontal, Metrics.inset).padding(.top, 10).padding(.bottom, 4)

            if let failure = engine.failure {
                Text(failure).font(.system(size: 11)).foregroundStyle(.red)
                    .padding(.horizontal, Metrics.inset).padding(.vertical, 6)
            } else if !engine.ready {
                HStack(spacing: 8) { ProgressView().controlSize(.small); Text("Starting…").foregroundStyle(.secondary) }
                    .font(.system(size: 11)).padding(.horizontal, Metrics.inset).padding(.vertical, 8)
            } else {
                cardSection
                Rule()
                destinationSection
                Rule()
                SectionHeading(title: "Tools")
                MenuRow(symbol: "camera.filters", title: "HDR Merge", detail: hdrDetail,
                        active: s.hdr_new.int > 0) { openHDR() }
                if let latest = s.update.latest.string {
                    MenuRow(symbol: "arrow.down", title: "Update to \(latest)", detail: "Copy Install Line", active: true) {
                        NSPasteboard.general.clearContents()
                        NSPasteboard.general.setString(s.update.line.str, forType: .string)
                        note = ("Install line copied. Paste it into Terminal.", false)
                    }
                }
            }
            Rule()
            footer
        }
        .padding(.bottom, 5)
        .frame(width: Metrics.width)
        .animation(.smooth(duration: 0.25), value: s.job.json)
        .onAppear { loginOn = System.opensAtLogin; Task { await engine.refresh() } }
    }

    // MARK: the card

    var card: J { s.cards[0] }
    var hasCard: Bool { !s.cards.array.isEmpty }
    var cardName: String {
        let n = s.cards.array.count
        return card.name.str + (n > 1 ? " and \(n - 1) more" : "")
    }

    /// What the card row says: its title stays the card's name; the line under it says what's
    /// happening, and the icon turns accent (needs you), green (safe) or red (a problem).
    struct CardStatus {
        var line: String
        var icon = "sdcard.fill"
        var active = false
        var tint: Color? = nil
        var progress: Double? = nil      // 0...1, or -1 while it's not known yet
        var progressLine: String? = nil
        var spinner = false
    }

    var status: CardStatus {
        let job = s.job, r = job.result, p = job.progress
        let kind = job.kind.str, st = job.state.str
        let fraction = p.exists ? p.done.double / max(p.total.double, 1) : -1

        if !s.dest.exists || !s.dest_drive_connected.bool {
            return CardStatus(line: counts(card.photos.int, card.videos.int).capitalizedFirst)
        }
        if !job.exists || (kind == "plan" && st == "running") {
            return CardStatus(line: p.exists ? "Reading \(p.done.int.formatted()) of \(plural(p.total.int, "file"))…"
                                              : "Looking for new photos and videos…", spinner: true)
        }
        if st == "error" { return CardStatus(line: job.error.str, icon: "exclamationmark", tint: .red) }
        if st == "running" && kind == "import" {
            return CardStatus(line: p.exists ? "Copying \(p.files_done.int.formatted()) of \(p.files_total.int.formatted())…" : "Starting…",
                              active: true, progress: fraction,
                              progressLine: p.exists ? "\(human(p.done.double)) of \(human(p.total.double))\(timeLeft(p))" : nil)
        }
        if st == "running" && kind == "verify" {
            return CardStatus(line: "Comparing every file byte by byte…", active: true, progress: fraction)
        }
        if kind == "plan" {
            if r.new_files.int == 0 { return CardStatus(line: "Everything is backed up", icon: "checkmark", tint: .green) }
            if !r.enough_space.bool {
                return CardStatus(line: "\(newCounts(r.new_photos.int, r.new_videos.int, r.new_xml.int).capitalizedFirst) · not enough space",
                                  icon: "exclamationmark", tint: .red)
            }
            return CardStatus(line: "\(newCounts(r.new_photos.int, r.new_videos.int, r.new_xml.int).capitalizedFirst) · \(human(r.needed_bytes.double))",
                              active: true)
        }
        if kind == "import" {
            let errs = r.errors.array.count
            return errs > 0
                ? CardStatus(line: "\(plural(errs, "file")) couldn't be copied", icon: "exclamationmark", tint: .red)
                : CardStatus(line: "Backed up \(counts(r.photos.int, r.videos.int, r.xml.int))", icon: "checkmark", tint: .green)
        }
        if kind == "verify" {
            let bad = r.cards.array.reduce(0) { $0 + $1.missing.array.count + $1.different.array.count }
            return bad > 0
                ? CardStatus(line: "\(plural(bad, "file")) not backed up yet", icon: "exclamationmark", tint: .red)
                : CardStatus(line: "Safe to format: every file is backed up", icon: "checkmark", tint: .green)
        }
        return CardStatus(line: counts(card.photos.int, card.videos.int).capitalizedFirst)
    }

    @ViewBuilder var cardSection: some View {
        SectionHeading(title: "Memory Card")
        if !hasCard {
            RowContent(symbol: "sdcard", title: "No Memory Card", subtitle: "Insert one to back it up.")
        } else {
            let st = status
            RowContent(symbol: st.icon, active: st.active, tint: st.tint, title: cardName, subtitle: st.line,
                       subtitleColor: st.tint == .red ? .red : nil) {
                if st.spinner { ProgressView().controlSize(.small) }
            }
            let photos = card.recent.strings.compactMap { image(fromDataURI: $0) }
            if !photos.isEmpty { PhotoStrip(photos: photos) }
            if let progress = st.progress {
                VStack(alignment: .leading, spacing: 3) {
                    if progress < 0 { ProgressView().progressViewStyle(.linear) }
                    else { ProgressView(value: min(max(progress, 0), 1)).progressViewStyle(.linear) }
                    if let line = st.progressLine {
                        Text(line).font(.system(size: 11)).monospacedDigit().foregroundStyle(.secondary)
                    }
                }
                .controlSize(.small)
                .padding(.leading, Metrics.text).padding(.trailing, Metrics.inset).padding(.vertical, 4)
            }
            if let note {
                Text(note.text).font(.system(size: 11)).foregroundStyle(note.bad ? Color.red : Color.secondary)
                    .padding(.leading, Metrics.text).padding(.trailing, Metrics.inset).padding(.bottom, 4)
            }
            cardActions
        }
    }

    // MARK: where it goes

    @ViewBuilder var destinationSection: some View {
        SectionHeading(title: "Back Up To")
        if !s.dest.exists {
            RowContent(symbol: "folder.badge.plus", title: "Choose a Folder", subtitle: "Where your photos and videos go")
            primary("Choose Folder…", pickBackup)
        } else {
            let (drive, folder) = place(s.dest.str)
            let connected = s.dest_drive_connected.bool
            RowContent(symbol: "externaldrive.fill", tint: connected ? nil : .red, title: drive,
                       subtitle: connected ? (folder ?? "Whole drive") : "Not connected. Plug in your backup drive.",
                       subtitleColor: connected ? nil : .red) {
                changeMenu
            }
            if showsFolders { FolderPreview(tree: s.job.result.tree) }
            if let next = mainAction { primary(next.0, next.1) }
        }
    }

    var showsFolders: Bool {
        let job = s.job
        return hasCard && job.kind.str == "plan" && job.state.str == "done" && job.result.new_files.int > 0
            && job.result.tree.exists
    }

    /// The one thing to do next, said exactly: "Back Up 6 Photos".
    var mainAction: (String, () -> Void)? {
        let job = s.job, r = job.result
        guard hasCard, s.dest_drive_connected.bool else { return nil }
        if job.state.str == "error" { return ("Try Again", retry) }
        guard job.kind.str == "plan", job.state.str == "done", r.new_files.int > 0, r.enough_space.bool else { return nil }
        let p = r.new_photos.int, v = r.new_videos.int + r.new_xml.int
        let what = v == 0 ? plural(p, "Photo") : p == 0 ? plural(r.new_videos.int, "Video") : "\(r.new_files.int.formatted()) Files"
        return ("Back Up \(what)", backUp)
    }

    func primary(_ title: String, _ run: @escaping () -> Void) -> some View {
        Button(action: run) { Text(title).frame(maxWidth: .infinity) }
            .mainAction(large: true)
            .keyboardShortcut(.defaultAction)
            .padding(.horizontal, Metrics.inset).padding(.top, 6).padding(.bottom, 4)
    }

    /// The recent backup folders, another one, and Finder.
    var changeMenu: some View {
        Menu {
            ForEach(s.recent_dests.strings, id: \.self) { path in
                Button { useBackup(path) } label: {
                    if path == s.dest.str { Label(placeName(path), systemImage: "checkmark") } else { Text(placeName(path)) }
                }
            }
            Divider()
            Button("Choose Folder…") { pickBackup() }
            Button("Show in Finder") { if let d = s.dest.string { System.showInFinder(d) } }
                .disabled(!s.dest_exists.bool)
        } label: {
            Text("Change").font(.system(size: 11, weight: .medium))
        }
        .menuStyle(.borderlessButton).menuIndicator(.hidden).fixedSize()
        .disabled(s.job.state.str == "running")
        .help("Choose where this backup goes")
    }

    func timeLeft(_ p: J) -> String {
        let done = p.done.double, total = p.total.double, t = p.elapsed.double
        guard t > 2, done > 0, done < total else { return "" }
        let left = (total - done) / (done / t)
        return left < 50 ? " — Less than a minute" : " — About \(plural(Int((left / 60).rounded(.up)), "minute"))"
    }

    // MARK: after a backup

    @ViewBuilder var cardActions: some View {
        let job = s.job, kind = job.kind.str
        let finished = job.state.str == "done" &&
            ((kind == "plan" && job.result.new_files.int == 0) || kind == "import" || kind == "verify")
        if finished {
            if kind != "verify" {
                MenuRow(symbol: "checkmark.shield", title: "Check Before Formatting") {
                    Task { await say(engine.act("/api/verify")) }
                }
            }
            if kind == "import", job.result.raw_jpg_pairs.int > 0 {
                MenuRow(symbol: "trash", title: "Move Extra JPGs to \(s.trash_name.str)",
                        detail: "\(job.result.raw_jpg_pairs.int)") { Task { await trash() } }
            }
            MenuRow(symbol: "eject", title: "Eject \(card.name.str)") { Task { await eject() } }
        }
    }

    var hdrDetail: String? {
        let j = s.hdr_job
        if j.state.str == "running" { return j.kind.str == "merge" ? "Merging…" : nil }
        let n = s.hdr_new.int
        return n > 0 ? "\(plural(n, "new set"))" : nil
    }

    // MARK: the bottom, like Wi-Fi's

    var footer: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack {
                Text("Open at Login").font(.system(size: 13))
                Spacer()
                Toggle("Open at Login", isOn: Binding(get: { loginOn },
                                                      set: { System.setOpensAtLogin($0); loginOn = System.opensAtLogin }))
                    .labelsHidden().toggleStyle(.switch).controlSize(.mini)
            }
            .padding(.horizontal, Metrics.inset).frame(height: 26)
            Button { NSApp.terminate(nil) } label: {
                HStack {
                    Text("Quit ShotLoft").font(.system(size: 13))
                    Spacer()
                    Text(s.version.str).font(.system(size: 11)).foregroundStyle(.tertiary)
                }
                .padding(.horizontal, Metrics.inset).frame(height: 26)
            }
            .buttonStyle(MenuRowStyle())
        }
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

extension String {
    /// "nothing" → "Nothing", for a count at the start of a sentence.
    var capitalizedFirst: String { prefix(1).uppercased() + dropFirst() }
}
