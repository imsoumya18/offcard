// The menu bar panel: the card, three chevrons, the drive — what goes where, centred, in ink — then
// HDR Merge and a one-line footer. It stays the same size in every state (360 × 279 pt), so it never
// jumps; things change in place: the card's icon becomes the copy ring and then the check, numbers
// roll, the chevrons run while copying.
//
// Colour: ink (white in dark mode, near-black in light) marks what matters now — the card with new
// files, the check, the one button. Red only for problems. Everything else is the system's greys.
// Type: 13 for names and rows, 11–11.5 for the lines under them.

import SwiftUI

/// The quiet accent for the login switch: the system graphite.
let brand = Color(nsColor: .systemGray)

enum Metrics {
    static let width: CGFloat = 360
    static let inset: CGFloat = 16
    static let icon: CGFloat = 40                    // the card's and the drive's icons
    static let arrow: CGFloat = 44                   // the chevrons' column between the tiles
    static var tile: CGFloat { (width - 2 * inset - arrow) / 2 }
    static let info: CGFloat = 48                    // the two centred lines (or the tag field), always this tall
    static let slot: CGFloat = 30                    // the button row, always this tall
    static let rowIcon: CGFloat = 28
}

/// Ink and its opposite, for the current appearance.
struct Ink {
    let scheme: ColorScheme
    var ink: Color { scheme == .dark ? .white : Color(white: 0.12) }
    var paper: Color { scheme == .dark ? Color(white: 0.1) : .white }
}

// MARK: building blocks

/// A round icon for a list row: quiet grey, or inked when it needs you.
struct RoundIcon: View {
    let symbol: String
    var active = false
    @Environment(\.colorScheme) private var scheme
    var body: some View {
        let c = Ink(scheme: scheme)
        Image(systemName: symbol)
            .font(.system(size: 12, weight: .semibold))
            .foregroundStyle(active ? c.paper : Color.primary)
            .frame(width: Metrics.rowIcon, height: Metrics.rowIcon)
            .background(Circle().fill(active ? c.ink : Color.primary.opacity(0.1)))
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
                .padding(.horizontal, 6))
            .onHover { hover = $0 }
    }
}

/// A clickable list row: icon, title, and a detail on the right.
struct MenuRow: View {
    let symbol: String
    let title: String
    var detail: String? = nil
    var active = false
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(spacing: 10) {
                RoundIcon(symbol: symbol, active: active)
                Text(title).font(.system(size: 13, weight: .medium)).foregroundStyle(.primary).lineLimit(1)
                Spacer(minLength: 6)
                if let detail { Text(detail).font(.system(size: 11)).foregroundStyle(.secondary).lineLimit(1) }
            }
            .padding(.horizontal, Metrics.inset).frame(height: 44)
        }
        .buttonStyle(MenuRowStyle())
    }
}

struct Hairline: View {
    var body: some View { Rectangle().fill(Color.primary.opacity(0.1)).frame(height: 1).padding(.horizontal, Metrics.inset) }
}

/// The liquid's surface: a gentle sine wave at `level` (0 empty, 1 full), calmer near either end.
struct Wave: Shape {
    var level: Double
    var phase: Double

    var animatableData: Double {
        get { level }
        set { level = newValue }
    }

    func path(in r: CGRect) -> Path {
        let surface = r.maxY - CGFloat(level) * r.height
        let height = 1.6 * sin(.pi * min(max(level, 0), 1)) + 0.3
        var path = Path()
        path.move(to: CGPoint(x: r.minX, y: r.maxY))
        for x in stride(from: r.minX, through: r.maxX, by: 1) {
            let angle = Double((x - r.minX) / r.width) * 2 * .pi * 1.1 + phase
            path.addLine(to: CGPoint(x: x, y: surface + CGFloat(sin(angle)) * height))
        }
        path.addLine(to: CGPoint(x: r.maxX, y: r.maxY))
        path.closeSubpath()
        return path
    }
}

/// What the big round icon at the top of a tile shows.
enum Mark: Equatable {
    case quiet(String)          // grey circle, symbol
    case ink(String)            // inked circle: it needs you, or it's done
    case alert(String)          // red: a problem
    case spinner                // checking
    case ring(Double)           // copying or verifying, 0...1
}

/// The big round icon. Its states turn into each other in place (card → ring → check).
struct BigBadge: View {
    let mark: Mark
    @Environment(\.colorScheme) private var scheme
    @Environment(\.accessibilityReduceMotion) private var still
    @State private var turn = false

    var body: some View {
        let c = Ink(scheme: scheme), s = Metrics.icon
        ZStack {
            switch mark {
            case .quiet(let sym):
                Circle().fill(Color.primary.opacity(0.1))
                Image(systemName: sym).font(.system(size: 16, weight: .semibold)).foregroundStyle(.primary)
                    .transition(.scale(scale: 0.6).combined(with: .opacity))
            case .ink(let sym):
                Circle().fill(c.ink)
                Image(systemName: sym).font(.system(size: 16, weight: .bold)).foregroundStyle(c.paper)
                    .id(sym)
                    .transition(.scale(scale: 0.5).combined(with: .opacity))
            case .alert(let sym):
                Circle().fill(Color.red)
                Image(systemName: sym).font(.system(size: 16, weight: .bold)).foregroundStyle(.white)
            case .spinner:
                Circle().fill(Color.primary.opacity(0.1))
                Circle().trim(from: 0, to: 0.28)
                    .stroke(c.ink, style: StrokeStyle(lineWidth: 2.5, lineCap: .round))
                    .padding(1.25)
                    .rotationEffect(.degrees(turn ? 360 : 0))
                    .animation(still ? nil : .linear(duration: 0.9).repeatForever(autoreverses: false), value: turn)
                    .onAppear { turn = true }
                Image(systemName: "sdcard.fill").font(.system(size: 14, weight: .semibold)).foregroundStyle(.secondary)
            case .ring(let p):
                LiquidRing(progress: p)
            }
        }
        .frame(width: s, height: s)
        .animation(.smooth(duration: 0.35), value: mark)
    }
}

/// The copy ring: ink arc, liquid rising inside, the percentage rolling. The engine reports every
/// half second; the level glides over the same time, so it never steps.
struct LiquidRing: View {
    let progress: Double
    @Environment(\.colorScheme) private var scheme
    @Environment(\.accessibilityReduceMotion) private var still

    var body: some View {
        let p = min(max(progress, 0), 1), c = Ink(scheme: scheme)
        TimelineView(.animation(minimumInterval: 1 / 30, paused: still)) { time in
            let t = still ? 0 : time.date.timeIntervalSinceReferenceDate
            ZStack {
                Circle().fill(Color.primary.opacity(0.08))
                ZStack {
                    Wave(level: p, phase: t * 1.7 + 2.1).fill(c.ink.opacity(0.12))
                    Wave(level: p, phase: t * 2.6).fill(c.ink.opacity(0.26))
                }
                .clipShape(Circle().inset(by: 4))
                Circle().stroke(Color.primary.opacity(0.12), lineWidth: 2.5)
                Circle().trim(from: 0, to: max(p, 0.004))
                    .stroke(c.ink, style: StrokeStyle(lineWidth: 2.5, lineCap: .round))
                    .rotationEffect(.degrees(-90))
                Text("\(Int(p * 100))%")
                    .font(.system(size: 11, weight: .semibold, design: .rounded)).monospacedDigit()
                    .contentTransition(.numericText(value: p))
            }
        }
        .animation(.linear(duration: 0.55), value: p)
        .accessibilityElement()
        .accessibilityLabel("\(Int(p * 100)) percent")
    }
}

/// One side of the route: the big icon, a name, and the line under it.
struct CenterTile<Sub: View>: View {
    let mark: Mark
    let title: String
    var dim = false
    @ViewBuilder var sub: Sub
    var body: some View {
        VStack(spacing: 8) {
            BigBadge(mark: mark)
            VStack(spacing: 1) {
                Text(title).font(.system(size: 13, weight: .semibold)).lineLimit(1)
                sub.font(.system(size: 11)).monospacedDigit().lineLimit(1)
            }
        }
        .frame(width: Metrics.tile)
        .opacity(dim ? 0.45 : 1)
    }
}

struct Chevron: Shape {
    func path(in r: CGRect) -> Path {
        var p = Path()
        p.move(to: CGPoint(x: r.minX, y: r.minY))
        p.addLine(to: CGPoint(x: r.maxX, y: r.midY))
        p.addLine(to: CGPoint(x: r.minX, y: r.maxY))
        return p
    }
}

/// The three chevrons between the card and the drive: quiet, stepping toward the drive; while
/// copying, inked, with a wave running through them every 0.8 s.
struct Chevrons: View {
    let active: Bool
    @Environment(\.colorScheme) private var scheme
    @Environment(\.accessibilityReduceMotion) private var still
    static let period = 0.8

    var body: some View {
        let ink = Ink(scheme: scheme).ink
        TimelineView(.animation(minimumInterval: 1 / 60, paused: !active || still)) { time in
            let phase = active && !still ? time.date.timeIntervalSinceReferenceDate.truncatingRemainder(dividingBy: Self.period) / Self.period : 0
            HStack(spacing: 2) {
                ForEach(0..<3, id: \.self) { i in
                    let base = [0.25, 0.5, 0.85][i]
                    let wave = 0.25 + 0.75 * max(0, sin((phase - Double(i) * 0.18) * 2 * .pi))
                    let o = active ? (still ? base : wave) : base * 0.6
                    Chevron()
                        .stroke(active ? ink.opacity(o) : Color.primary.opacity(o),
                                style: StrokeStyle(lineWidth: 2.4, lineCap: .round, lineJoin: .round))
                        .frame(width: 6, height: 12)
                        .padding(.horizontal, 2)
                }
            }
        }
        .frame(width: 132, height: Metrics.icon)
        .animation(.smooth(duration: 0.3), value: active)
        .accessibilityHidden(true)
    }
}

/// The one thing to do next, or a quiet line in its place: always one row of the same height.
enum Slot {
    case ink(String, () -> Void)
    case split(String, () -> Void, () -> Void)        // the main action, and its ⌄ for the other choices
    case inkPair(String, () -> Void, String, () -> Void)
    case quiet(String, () -> Void)
    case disabled(String)
    case text(String)
}

struct SlotView: View {
    let slot: Slot
    @Environment(\.colorScheme) private var scheme

    var body: some View {
        let c = Ink(scheme: scheme)
        SwiftUI.Group {
            switch slot {
            case .ink(let title, let run):
                Button(action: run) { pill(title, fg: c.paper, bg: c.ink) }
                    .buttonStyle(PressStyle()).keyboardShortcut(.defaultAction)
            case .split(let title, let run, let more):
                HStack(spacing: 0) {
                    Button(action: run) {
                        Text(title).font(.system(size: 13, weight: .semibold)).foregroundStyle(c.paper).lineLimit(1)
                            .frame(maxWidth: .infinity).frame(height: Metrics.slot).contentShape(Rectangle())
                    }
                    .buttonStyle(PressStyle()).keyboardShortcut(.defaultAction)
                    Rectangle().fill(c.paper.opacity(0.25)).frame(width: 1, height: 16)
                    Button(action: more) {
                        Image(systemName: "chevron.down").font(.system(size: 10, weight: .bold)).foregroundStyle(c.paper)
                            .frame(width: 40, height: Metrics.slot).contentShape(Rectangle())
                    }
                    .buttonStyle(PressStyle()).help("Back up only some files, or tag the day").accessibilityLabel("More backup choices")
                }
                .background(Capsule().fill(c.ink)).clipShape(Capsule())
            case .inkPair(let title, let run, let second, let run2):
                HStack(spacing: 8) {
                    Button(action: run) { pill(title, fg: c.paper, bg: c.ink) }
                        .buttonStyle(PressStyle()).keyboardShortcut(.defaultAction)
                    Button(action: run2) { pill(second, fg: .primary, bg: Color.primary.opacity(0.12)).frame(width: 92) }
                        .buttonStyle(PressStyle())
                }
            case .quiet(let title, let run):
                Button(action: run) { pill(title, fg: .primary, bg: Color.primary.opacity(0.12)) }.buttonStyle(PressStyle())
            case .disabled(let title):
                pill(title, fg: Color.primary.opacity(0.3), bg: Color.primary.opacity(0.06))
            case .text(let line):
                Text(line).font(.system(size: 11.5)).monospacedDigit().foregroundStyle(.secondary)
                    .contentTransition(.numericText())
                    .frame(maxWidth: .infinity).frame(height: Metrics.slot)
            }
        }
    }

    func pill(_ title: String, fg: Color, bg: Color) -> some View {
        Text(title).font(.system(size: 13, weight: .semibold)).foregroundStyle(fg).lineLimit(1)
            .frame(maxWidth: .infinity).frame(height: Metrics.slot)
            .background(Capsule().fill(bg))
            .contentShape(Capsule())
    }
}

/// Quit, highlighted under the pointer like a menu item; ⌘Q works too.
struct QuitButton: View {
    @State private var hover = false
    var body: some View {
        Button { NSApp.terminate(nil) } label: {
            Text("Quit").font(.system(size: 11, weight: .medium))
                .foregroundStyle(hover ? AnyShapeStyle(.primary) : AnyShapeStyle(.secondary))
                .padding(.horizontal, 9).frame(height: 22)
                .background(Capsule().fill(Color.primary.opacity(hover ? 0.1 : 0)))
                .contentShape(Capsule())
        }
        .buttonStyle(PressStyle())
        .keyboardShortcut("q")
        .onHover { hover = $0 }
        .animation(.easeOut(duration: 0.12), value: hover)
        .help("Quit offcard (⌘Q)")
    }
}

/// Buttons dim a touch while pressed.
struct PressStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label.opacity(configuration.isPressed ? 0.75 : 1)
            .animation(.easeOut(duration: 0.12), value: configuration.isPressed)
    }
}

/// "Backup Drive › Sony Backup" for /Volumes/Backup Drive/Photos/Sony Backup.
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

// MARK: the panel

struct PanelView: View {
    @EnvironmentObject var engine: Engine
    @EnvironmentObject var model: AppModel
    @Environment(\.colorScheme) private var scheme
    @State private var note: (text: String, bad: Bool)?
    @State private var loginOn = System.opensAtLogin

    @State private var path: [Page] = []          // the pages over the backup page, deepest last
    @State private var backupHeight: CGFloat = 293
    @State private var editingDay: String?         // the day whose tag is being typed on this page

    enum Page: Hashable { case hdr, days, files(String) }

    var s: J { engine.state }

    /// Both pages side by side; the panel slides between them. The HDR page takes the backup
    /// page's height, so the popup never changes size.
    var body: some View {
        ZStack(alignment: .topLeading) {
            backupPage
                .background(GeometryReader { g in Color.clear.preference(key: HeightKey.self, value: g.size.height) })
                .offset(x: path.isEmpty ? 0 : -Metrics.width)
                .allowsHitTesting(path.isEmpty)
                .accessibilityHidden(!path.isEmpty)
            ForEach(Array(path.enumerated()), id: \.element) { k, p in
                page(p)
                    .frame(width: Metrics.width, height: backupHeight)
                    .offset(x: k == path.count - 1 ? 0 : -Metrics.width)
                    .allowsHitTesting(k == path.count - 1)
                    .accessibilityHidden(k != path.count - 1)
                    .transition(.move(edge: .trailing))
            }
        }
        .frame(width: Metrics.width, alignment: .top)
        .clipped()
        .onPreferenceChange(HeightKey.self) { backupHeight = $0 }
    }

    @ViewBuilder func page(_ p: Page) -> some View {
        switch p {
        case .hdr:
            HDRPage(model: model.hdr, back: pop)
        case .days:
            DaysPage(choice: model.choice, back: pop, open: { push(.files($0)) }, tag: setTag, backUp: backUp)
        case .files(let day):
            DayFilesPage(choice: model.choice, day: day, back: pop, backUp: backUp)
        }
    }

    func push(_ p: Page) {
        editingDay = nil
        withAnimation(.smooth(duration: 0.32)) { path.append(p) }
    }

    func pop() {
        withAnimation(.smooth(duration: 0.32)) { _ = path.popLast() }
    }

    @ViewBuilder var backupPage: some View {
        let v = view
        VStack(spacing: 0) {
            ZStack(alignment: .top) {
                HStack(alignment: .top, spacing: 0) {
                    CenterTile(mark: v.card, title: v.cardTitle, dim: v.cardDim) {
                        Text(v.cardLine).foregroundStyle(v.cardBad ? AnyShapeStyle(Color.red) : AnyShapeStyle(.secondary))
                            .contentTransition(.numericText())
                    }
                    Color.clear.frame(width: Metrics.arrow, height: Metrics.icon)
                    CenterTile(mark: v.drive, title: v.driveTitle) { destination(v) }
                }
                Chevrons(active: v.copying)
            }
            .padding(.top, 18)

            VStack(spacing: 4) {
                if v.tagLine { readyInfo }
                ForEach(Array(v.info.enumerated()), id: \.offset) { _, line in
                    line.multilineTextAlignment(.center).lineLimit(1).truncationMode(.middle)
                }
                if let action = v.infoAction {
                    Button(action: action.run) {
                        Text(action.title).font(.system(size: 11, weight: .medium)).underline().foregroundStyle(.primary)
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(.horizontal, Metrics.inset)
            .frame(maxWidth: .infinity).frame(height: Metrics.info)
            .padding(.top, 12)

            SlotView(slot: v.slot).padding(.horizontal, Metrics.inset).padding(.top, 10).padding(.bottom, 14)

            Hairline()
            if let latest = s.update.latest.string {
                MenuRow(symbol: "arrow.down", title: "Update to \(latest)", detail: "Copy Install Line", active: true) {
                    NSPasteboard.general.clearContents()
                    NSPasteboard.general.setString(s.update.line.str, forType: .string)
                    note = ("Install line copied. Paste it into Terminal.", false)
                }
                Hairline()
            }
            MenuRow(symbol: "camera.filters", title: "HDR Merge", detail: hdrDetail) { openHDR() }
            Hairline()
            footer
        }
        .frame(width: Metrics.width)
        .animation(.smooth(duration: 0.3), value: s.job.json)
        .onAppear { loginOn = System.opensAtLogin; Task { await engine.refresh() } }
    }

    // MARK: what each state shows

    struct PanelState {
        var card: Mark = .ink("sdcard.fill")
        var cardTitle = ""
        var cardLine = ""
        var cardBad = false
        var cardDim = false
        var drive: Mark = .quiet("externaldrive.fill")
        var driveTitle = ""
        var driveLine: String? = nil         // replaces the folder under the drive's name
        var driveBad = false
        var copying = false
        var info: [Text] = []
        var infoAction: (title: String, run: () -> Void)? = nil    // a clickable second line
        var tagLine = false                  // ready to back up: the day's folder with its tag
        var slot: Slot = .disabled("Back Up")
    }

    var card: J { s.cards[0] }
    var hasCard: Bool { !s.cards.array.isEmpty }
    var cardName: String {
        let n = s.cards.array.count
        return card.name.str + (n > 1 ? " +\(n - 1)" : "")
    }
    var drive: String { place(s.dest.str).drive }

    var view: PanelState {
        var v = PanelState()
        let job = s.job, r = job.result, p = job.progress
        let kind = job.kind.str, st = job.state.str
        let fraction = p.exists ? p.done.double / max(p.total.double, 1) : 0

        // the drive
        if !s.dest.exists {
            v.drive = .quiet("folder.badge.plus"); v.driveTitle = "Choose"; v.driveLine = "a backup folder"
        } else {
            v.driveTitle = drive
            if !s.dest_drive_connected.bool { v.drive = .alert("exclamationmark"); v.driveLine = "Not connected"; v.driveBad = true }
        }

        // the card
        guard engine.ready else {
            v.card = .spinner; v.cardTitle = "offcard"; v.cardLine = "Starting…"
            v.info = [line(engine.failure ?? "Getting ready", bad: engine.failure != nil)]
            return v
        }
        guard hasCard else {
            v.card = .quiet("sdcard"); v.cardTitle = "No card"; v.cardLine = "Insert one"; v.cardDim = true
            v.info = [line("Put a memory card in to see what's new"), noteLine ?? line("offcard only ever reads it")]
            if !s.dest.exists { v.slot = .ink("Choose Folder…", pickBackup) }
            return v
        }
        v.cardTitle = cardName
        v.cardLine = counts(card.photos.int, card.videos.int).capitalizedFirst

        if !s.dest.exists {
            v.info = [line("Choose where your photos and videos go"), line("offcard remembers it for next time")]
            v.slot = .ink("Choose Folder…", pickBackup)
            return v
        }
        if !s.dest_drive_connected.bool {
            v.info = [line("Plug in \(drive) to back up", bad: true), line("or choose another folder")]
            v.slot = .quiet("Choose Another Folder…", pickBackup)
            return v
        }
        if !job.exists || (kind == "plan" && st == "running") {
            v.card = .spinner; v.cardLine = "Checking…"
            v.info = [line(p.exists ? "Reading \(p.done.int.formatted()) of \(plural(p.total.int, "file"))" : "Looking for what's new"),
                      line("The card is only ever read")]
            return v
        }
        if st == "error" {
            v.card = .alert("exclamationmark"); v.cardLine = "Couldn't finish"; v.cardBad = true
            v.info = [line(job.error.str, bad: true), line("Nothing on the card was changed")]
            v.slot = .ink("Try Again", retry)
            return v
        }
        if st == "running" && kind == "import" {
            v.card = .ring(fraction); v.copying = true
            v.cardLine = p.exists ? amountOf(p.done.double, p.total.double) : "Starting…"
            v.info = destinationLines(fallback: "Copying to \(drive)")
            v.slot = .text(timeLeft(p) ?? "Copying…")
            return v
        }
        if st == "running" && kind == "verify" {
            v.card = .ring(fraction); v.copying = true; v.cardLine = "Comparing…"
            v.info = [line("Comparing every file byte by byte"),
                      line(p.files_total.int > 0 ? "\(p.files_done.int.formatted()) of \(p.files_total.int.formatted()) checked" : "Reading the card and the copies")]
            v.slot = .text(timeLeft(p) ?? "Checking…")
            return v
        }
        if kind == "plan" {
            if r.new_files.int == 0 {
                v.card = .ink("checkmark"); v.cardLine = "All backed up"
                v.info = [line("Nothing new since your last backup"),
                          noteLine ?? line("\(counts(card.photos.int, card.videos.int).capitalizedFirst), all on \(drive)")]
                v.slot = .inkPair("Check Before Formatting", verify, "Eject", eject)
            }
            let c = model.choice, partial = !c.everything && !c.files.isEmpty
            let needed = partial ? c.bytes() : r.needed_bytes.double
            if needed + 50 * 1_048_576 > r.free_bytes.double {
                v.cardLine = "\(partial ? c.count() : r.new_files.int) new · \(human(needed))"
                v.drive = .alert("exclamationmark"); v.driveLine = "\(human(r.free_bytes.double)) free"; v.driveBad = true
                v.info = [line("Needs \(human(max(0, needed - r.free_bytes.double))) more on \(drive)", bad: true),
                          line("Back up some files now, or choose another folder")]
                v.slot = .inkPair("Choose Files…", { push(.days) }, "Change", pickBackup)
            } else {
                v.cardLine = partial ? "\(c.count().formatted()) of \(r.new_files.int.formatted()) new · \(human(c.bytes()))"
                                     : "\(r.new_files.int.formatted()) new · \(human(r.needed_bytes.double))"
                v.tagLine = true
                let title = partial ? "Back Up \(plural(c.count(), "File"))" : backUpTitle(r)
                v.slot = st != "done" ? .disabled("Back Up") : partial && c.count() == 0 ? .disabled("Back Up")
                    : .split(title, backUp, moreMenu)
            }
            return v
        }
        if kind == "import" {
            let errs = r.errors.array.count
            if errs > 0 {
                v.card = .alert("exclamationmark"); v.cardLine = "\(plural(errs, "file")) not copied"; v.cardBad = true
                v.info = [line("\(plural(errs, "file")) couldn't be copied", bad: true), line("Try again, or check the card and the drive")]
                v.slot = .ink("Try Again", retry)
            } else {
                v.card = .ink("checkmark"); v.cardLine = "Backed up \(plural(r.files.int, "file"))"
                let days = r.days.strings
                let filed = days.isEmpty ? line("Filed by day on \(drive)")
                    : line("Filed in \(days[0].replacingOccurrences(of: "/", with: " › "))" + (days.count > 1 ? " +\(days.count - 1)" : ""))
                if let n = noteLine {
                    v.info = [filed, n]
                } else if r.raw_jpg_pairs.int > 0 {
                    v.info = [filed]
                    v.infoAction = ("Move \(plural(r.raw_jpg_pairs.int, "extra JPG")) to the \(s.trash_name.str)", { Task { await trash() } })
                } else {
                    v.info = [filed, line("Check it before you format the card")]
                }
                v.slot = .inkPair("Check Before Formatting", verify, "Eject", eject)
            }
            return v
        }
        if kind == "verify" {
            let bad = r.cards.array.reduce(0) { $0 + $1.missing.array.count + $1.different.array.count }
            if bad > 0 {
                v.card = .alert("exclamationmark"); v.cardLine = "\(plural(bad, "file")) not backed up"; v.cardBad = true
                v.info = [line("\(plural(bad, "file")) aren't on \(drive) yet", bad: true), line("Back up again before you format the card")]
                v.slot = .ink("Back Up Again", retry)
            } else {
                v.card = .ink("checkmark"); v.cardLine = "Safe to format"
                v.info = [line("Every file is on \(drive), byte for byte"), noteLine ?? line("You can format the card in the camera")]
                v.slot = .ink("Eject \(card.name.str)", eject)
            }
            return v
        }
        return v
    }

    /// Ready to back up: the day's folder, named for its tag, with "+ Add tag" (typed in place); or,
    /// for a card with several days, how many and "Add tags ›", which opens each day on its own.
    @ViewBuilder var readyInfo: some View {
        let r = s.job.result, days = r.days.array, c = model.choice
        let partial = !c.everything && !c.files.isEmpty
        if days.count == 1, let d = days.first {
            let key = d.key.str
            if editingDay == key {
                TagField(day: key, start: d.tag.str, recent: s.recent_tags.strings,
                         commit: { setTag(key, $0); editingDay = nil }, cancel: { editingDay = nil })
            } else {
                HStack(spacing: 5) {
                    folderText(d).lineLimit(1).truncationMode(.middle)
                    if d.tag.str.isEmpty {
                        AddTagButton { editingDay = key }
                    } else {
                        Button { editingDay = key } label: {
                            Image(systemName: "pencil").font(.system(size: 10, weight: .semibold)).foregroundStyle(.tertiary)
                                .frame(width: 18, height: 18).contentShape(Rectangle())
                        }
                        .buttonStyle(PressStyle()).help("Change this day's tag")
                    }
                }
                secondLine(partial: partial) {
                    line([r.new_photos.int > 0 ? "Photos \(r.new_photos.int.formatted())" : nil,
                          r.new_videos.int > 0 ? "Videos \(r.new_videos.int.formatted())" : nil].compactMap { $0 }.joined(separator: "  ·  "))
                }
            }
        } else {
            HStack(spacing: 5) {
                Image(systemName: "folder.fill").font(.system(size: 10.5)).foregroundStyle(.tertiary)
                Text("\(days.count) days · \(dayRange(days.map(\.key.str)))").font(.system(size: 11.5))
            }
            secondLine(partial: partial) {
                let tagged = days.filter { !$0.tag.str.isEmpty }
                Button { push(.days) } label: {
                    if tagged.isEmpty {
                        (Text("Add tags  ") + Text(Image(systemName: "chevron.right")).foregroundStyle(.secondary))
                            .font(.system(size: 11, weight: .medium)).foregroundStyle(.primary)
                            .padding(.horizontal, 9).frame(height: 20).background(Capsule().fill(Color.primary.opacity(0.1)))
                    } else {
                        let names = Array(NSOrderedSet(array: tagged.map(\.tag.str))).compactMap { $0 as? String }
                        (Text("\(tagged.count) tagged: \(names.prefix(2).joined(separator: ", "))\(names.count > 2 ? "…" : "")  ·  ").foregroundStyle(.secondary)
                         + Text("Add tags").foregroundStyle(.primary) + Text(" ›").foregroundStyle(.secondary))
                            .font(.system(size: 11)).lineLimit(1)
                    }
                }
                .buttonStyle(PressStyle()).help("Tag each day on its own")
            }
        }
    }

    /// The middle's second line: a note if there is one, "N left for later · Change" when only some
    /// files are chosen, else the given line.
    @ViewBuilder func secondLine<Normal: View>(partial: Bool, @ViewBuilder _ normal: () -> Normal) -> some View {
        if let n = noteLine {
            n
        } else if partial {
            Button { push(.days) } label: {
                (Text("\(plural(model.choice.totalFiles - model.choice.count(), "file")) left for later  ·  ").foregroundStyle(.secondary)
                 + Text("Change").underline().foregroundStyle(.primary)).font(.system(size: 11))
            }
            .buttonStyle(.plain)
        } else {
            normal()
        }
    }

    /// The day's folder as it will be: path, then its name (with the tag), and "new" if it's new.
    func folderText(_ d: J) -> Text {
        let parts = d.folder.str.split(separator: "/").map(String.init)
        var t = Text(Image(systemName: "folder.fill")).foregroundStyle(.tertiary)
            + Text("  " + parts.dropLast().joined(separator: " › ") + (parts.count > 1 ? " › " : "")).foregroundStyle(.secondary)
            + Text(parts.last ?? "").foregroundStyle(.primary)
        if d.new.bool { t = t + Text("  new").foregroundStyle(.secondary) }
        return t.font(.system(size: 11.5))
    }

    /// The Back Up button's ⌄: everything (the default), only photos or videos, choosing, tagging.
    func moreMenu() {
        let c = model.choice, r = s.job.result, days = r.days.array
        let photos = c.files.filter { !$0.isVideo }.reduce(0) { $0 + $1.files }
        let videos = c.files.filter(\.isVideo).reduce(0) { $0 + $1.files }
        var items: [System.MenuItem] = [
            .init(title: "Everything", detail: "\(r.new_files.int)", checked: c.everything) { c.chosen = nil },
        ]
        if photos > 0 && videos > 0 {
            items += [.init(title: "Photos Only", detail: "\(photos)") { c.only { !$0.isVideo } },
                      .init(title: "Videos Only", detail: "\(videos)") { c.only(\.isVideo) }]
        }
        items += [.separator, .init(title: "Choose Files…") { push(.days) }, .separator]
        if days.count == 1, let key = days.first?.key.str {
            items.append(.init(title: days[0].tag.str.isEmpty ? "Add Tag…" : "Change Tag…") { editingDay = key })
        } else {
            items.append(.init(title: "Add Tags…") { push(.days) })
        }
        System.popUpMenu(items)
    }

    func line(_ s: String, bad: Bool = false) -> Text {
        Text(s).font(.system(size: 11)).foregroundStyle(bad ? AnyShapeStyle(Color.red) : AnyShapeStyle(.secondary))
    }

    var noteLine: Text? { note.map { line($0.text, bad: $0.bad) } }

    /// Where a backup goes, in two lines: the first day's folder (the new part marked), then what goes in.
    func destinationLines(fallback: String) -> [Text] {
        let r = s.job.kind.str == "plan" ? s.job.result : model.lastPlan, days = r.days.array
        let counts = [r.new_photos.int > 0 ? "Photos \(r.new_photos.int.formatted())" : nil,
                      r.new_videos.int > 0 ? "Videos \(r.new_videos.int.formatted())" : nil].compactMap { $0 }
        guard let first = days.first?.folder.string else {
            return [line(fallback), line(counts.joined(separator: "  ·  "))]
        }
        let parts = first.split(separator: "/").map(String.init)
        let isNew = dayIsNew(parts, in: r.tree)
        var t = Text(Image(systemName: "folder.fill")).foregroundStyle(.tertiary)
            + Text("  " + parts.dropLast().joined(separator: " › ") + (parts.count > 1 ? " › " : "")).foregroundStyle(.secondary)
            + Text(parts.last ?? "").foregroundStyle(.primary)
        if isNew { t = t + Text("  new").foregroundStyle(.secondary) }
        if days.count > 1 { t = t + Text("  +\(days.count - 1) more").foregroundStyle(.secondary) }
        return [t.font(.system(size: 11.5)), line(counts.joined(separator: "  ·  "))]
    }

    /// Whether the plan's folder tree marks this day folder as new.
    func dayIsNew(_ parts: [String], in tree: J) -> Bool {
        var node = tree
        for part in parts {
            guard let next = node.children.array.first(where: { $0.name.str == part }) else { return false }
            node = next
        }
        return node.new.bool
    }

    /// "Back Up 148 Files", "Back Up 6 Photos".
    func backUpTitle(_ r: J) -> String {
        let p = r.new_photos.int, v = r.new_videos.int + r.new_xml.int
        let what = v == 0 ? plural(p, "Photo") : p == 0 ? plural(r.new_videos.int, "Video") : "\(r.new_files.int.formatted()) Files"
        return "Back Up \(what)"
    }

    /// The folder under the drive's name, as a menu: recent folders, another one, Finder.
    @ViewBuilder func destination(_ v: PanelState) -> some View {
        if let text = v.driveLine {
            Text(text).foregroundStyle(v.driveBad ? AnyShapeStyle(Color.red) : AnyShapeStyle(.secondary))
        } else {
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
                Text("\(place(s.dest.str).folder ?? "Whole drive") \(Image(systemName: "chevron.up.chevron.down"))")
                    .foregroundStyle(.secondary)
            }
            .menuStyle(.borderlessButton).menuIndicator(.hidden).fixedSize()
            .disabled(s.job.state.str == "running")
            .help("Choose where this backup goes")
        }
    }

    /// "2.2 of 5.7 GB": both in the total's unit, the unit said once.
    func amountOf(_ done: Double, _ total: Double) -> String {
        let f = ByteCountFormatter()
        f.countStyle = .binary
        f.allowedUnits = total >= 1_073_741_824 ? .useGB : total >= 1_048_576 ? .useMB : .useKB
        let whole = f.string(fromByteCount: Int64(total))
        f.includesUnit = false
        return "\(f.string(fromByteCount: Int64(done))) of \(whole)"
    }

    /// "About 2 minutes left", once there's enough to go on.
    func timeLeft(_ p: J) -> String? {
        let done = p.done.double, total = p.total.double, t = p.elapsed.double
        guard t > 2, done > 0, done < total else { return nil }
        let left = (total - done) / (done / t)
        return left < 50 ? "Less than a minute left" : "About \(plural(Int((left / 60).rounded(.up)), "minute")) left"
    }

    var hdrDetail: String? {
        let j = s.hdr_job
        if j.state.str == "running" { return j.kind.str == "merge" ? "Merging…" : nil }
        let n = s.hdr_new.int
        return n > 0 ? "\(plural(n, "new set"))" : nil
    }

    // MARK: the footer: preferences, not features

    /// A quiet tray along the bottom: the login switch, the version, and Quit.
    var footer: some View {
        HStack(spacing: 6) {
            Toggle("Open at Login", isOn: Binding(get: { loginOn }, set: { setLogin($0) }))
                .labelsHidden().toggleStyle(.switch).controlSize(.mini).tint(brand)
            Text("Open at Login").font(.system(size: 11)).foregroundStyle(.secondary)
                .contentShape(Rectangle())
                .onTapGesture { setLogin(!loginOn) }
            Spacer(minLength: 6)
            Text("v\(appVersion)").font(.system(size: 11)).monospacedDigit().foregroundStyle(.tertiary)
                .help("The version of offcard you have")
            QuitButton()
        }
        .padding(.leading, Metrics.inset).padding(.trailing, 8).frame(height: 34)
        .background(Color.primary.opacity(0.035))
    }

    var appVersion: String {
        Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? s.version.str
    }

    func setLogin(_ on: Bool) {
        System.setOpensAtLogin(on)
        loginOn = System.opensAtLogin
    }

    // MARK: actions

    func say(_ error: String?) async {
        withAnimation { note = error.map { ($0, true) } }
    }

    func backUp() {
        note = nil
        let c = model.choice
        let body: [String: Any] = c.everything ? [:] : ["ids": Array(c.picked).sorted()]
        Task { await say(engine.act("/api/import", body)) }
    }

    func setTag(_ day: String, _ tag: String) {
        Task { await say(engine.act("/api/tag", ["day": day, "tag": tag])) }
    }

    func verify() { note = nil; Task { await say(engine.act("/api/verify")) } }

    func retry() { note = nil; Task { await engine.act("/api/reset"); model.replan() } }

    func useBackup(_ path: String) {
        guard path != s.dest.str else { return }
        Task { await say(engine.act("/api/dest", ["path": path])); model.replan() }
    }

    func pickBackup() {
        guard let path = System.chooseFolder("Choose where offcard backs up your photos and videos", startingAt: s.dest.string) else { return }
        Task { await say(engine.act("/api/dest", ["path": path])); model.replan() }
    }

    func eject() {
        Task {
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
    }

    func trash() async {
        do {
            let r = try await engine.call("/api/trash", [:])
            note = ("Moved \(plural(r.moved.int, "JPG")) to the \(s.trash_name.str).", false)
        } catch { note = (error.localizedDescription, true) }
        await engine.refresh()
    }

    func openHDR() { push(.hdr) }
}

struct HeightKey: PreferenceKey {
    static let defaultValue: CGFloat = 281
    static func reduce(value: inout CGFloat, nextValue: () -> CGFloat) { value = nextValue() }
}

extension String {
    /// "nothing" → "Nothing", for a count at the start of a sentence.
    var capitalizedFirst: String { prefix(1).uppercased() + dropFirst() }
}

