// The menu bar panel: the card, the backup drive, and the tools, on the system's Liquid Glass.

import SwiftUI

let brand = Color(red: 0.0, green: 0.56, blue: 0.56)

// MARK: building blocks

/// A quiet surface on the glass (Apple: don't stack glass on glass; use fills inside it).
struct Surface: ViewModifier {
    var radius: CGFloat = 14
    func body(content: Content) -> some View {
        content.background(.fill.quinary, in: RoundedRectangle(cornerRadius: radius, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: radius, style: .continuous)
                .strokeBorder(.separator.opacity(0.5), lineWidth: 0.5))
    }
}

extension View {
    func surface(_ radius: CGFloat = 14) -> some View { modifier(Surface(radius: radius)) }

    /// The main action: a tinted Liquid Glass button on macOS 26, a prominent one before.
    @ViewBuilder func primaryAction() -> some View {
        #if compiler(>=6.2)
        if #available(macOS 26.0, *) {
            self.buttonStyle(.glassProminent).tint(brand).controlSize(.large)
        } else {
            self.buttonStyle(.borderedProminent).tint(brand).controlSize(.large)
        }
        #else
        self.buttonStyle(.borderedProminent).tint(brand).controlSize(.large)
        #endif
    }
}

/// A row in a group: icon, title, detail, and a chevron; highlights on hover like a menu item.
struct RowStyle: ButtonStyle {
    @State private var hover = false
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .contentShape(Rectangle())
            .background(RoundedRectangle(cornerRadius: 9, style: .continuous)
                .fill(configuration.isPressed ? AnyShapeStyle(.fill.secondary)
                      : hover ? AnyShapeStyle(.fill.tertiary) : AnyShapeStyle(.clear)))
            .onHover { hover = $0 }
            .animation(.easeOut(duration: 0.12), value: hover)
    }
}

struct Row: View {
    let symbol: String
    let title: String
    var detail: String? = nil
    var tint: Color = brand
    var chevron = true
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(spacing: 11) {
                Image(systemName: symbol)
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundStyle(tint)
                    .frame(width: 28, height: 28)
                    .background(tint.opacity(0.14), in: RoundedRectangle(cornerRadius: 8, style: .continuous))
                VStack(alignment: .leading, spacing: 1) {
                    Text(title).font(.system(size: 13, weight: .medium)).foregroundStyle(.primary)
                    if let detail {
                        Text(detail).font(.system(size: 11.5)).foregroundStyle(.secondary).lineLimit(1)
                    }
                }
                Spacer(minLength: 4)
                if chevron {
                    Image(systemName: "chevron.right").font(.system(size: 10, weight: .bold)).foregroundStyle(.tertiary)
                }
            }
            .padding(.horizontal, 8).padding(.vertical, 7)
        }
        .buttonStyle(RowStyle())
    }
}

struct RowGroup<Content: View>: View {
    let title: String
    @ViewBuilder let content: Content
    var body: some View {
        VStack(alignment: .leading, spacing: 5) {
            Text(title).font(.system(size: 11, weight: .semibold)).foregroundStyle(.secondary)
                .padding(.leading, 6)
            VStack(spacing: 0) { content }.padding(4).surface(13)
        }
    }
}

struct Ring: View {
    let fraction: Double?   // nil: still starting, spins
    @State private var spin = false
    var body: some View {
        ZStack {
            Circle().stroke(.fill.tertiary, lineWidth: 3.5)
            Circle().trim(from: 0, to: fraction.map { max(0.02, min($0, 1)) } ?? 0.28)
                .stroke(brand.gradient, style: StrokeStyle(lineWidth: 3.5, lineCap: .round))
                .rotationEffect(.degrees(fraction == nil ? (spin ? 270 : -90) : -90))
                .animation(fraction == nil ? .linear(duration: 1).repeatForever(autoreverses: false) : .smooth,
                           value: fraction == nil ? spin : (fraction ?? 0) > 0)
            if let fraction {
                Text("\(Int(fraction * 100))").font(.system(size: 10.5, weight: .semibold, design: .rounded))
                    .monospacedDigit().contentTransition(.numericText())
            }
        }
        .frame(width: 38, height: 38)
        .onAppear { spin = true }
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
        VStack(alignment: .leading, spacing: 12) {
            header
            if let failure = engine.failure {
                Label(failure, systemImage: "exclamationmark.triangle.fill").foregroundStyle(.red).font(.callout)
            } else if !engine.ready {
                HStack(spacing: 10) { ProgressView().controlSize(.small); Text("Starting…").foregroundStyle(.secondary) }
                    .frame(maxWidth: .infinity, minHeight: 90)
            } else {
                hero
                if let note {
                    Label(note.text, systemImage: note.bad ? "exclamationmark.circle.fill" : "checkmark.circle.fill")
                        .font(.callout).foregroundStyle(note.bad ? Color.red : Color.green)
                        .transition(.opacity.combined(with: .move(edge: .top)))
                }
                if let latest = s.update.latest.string { updateBanner(latest) }
                cardActions
                drive
                RowGroup(title: "Tools") {
                    Row(symbol: "square.stack.3d.up.fill", title: "HDR Merge",
                        detail: hdrDetail) { openHDR() }
                }
            }
            footer
        }
        .padding(14)
        .frame(width: 340)
        .animation(.smooth(duration: 0.25), value: s.json)
        .onAppear { loginOn = System.opensAtLogin; Task { await engine.refresh() } }
    }

    // MARK: header and footer

    var header: some View {
        HStack(spacing: 8) {
            Image(nsImage: NSApp.applicationIconImage).resizable().frame(width: 22, height: 22)
            Text("ShotLoft").font(.system(size: 13.5, weight: .semibold))
            if let v = s.version.string { Text(v).font(.system(size: 11)).foregroundStyle(.tertiary) }
            Spacer()
            Menu {
                Toggle("Open at Login", isOn: Binding(get: { loginOn }, set: { System.setOpensAtLogin($0); loginOn = System.opensAtLogin }))
                Button("Change Backup Folder…") { pickBackup() }
                Divider()
                Button("Quit ShotLoft") { NSApp.terminate(nil) }
            } label: {
                Image(systemName: "ellipsis.circle").font(.system(size: 15)).foregroundStyle(.secondary)
            }
            .menuStyle(.borderlessButton).menuIndicator(.hidden).fixedSize()
        }
        .padding(.horizontal, 2)
    }

    var footer: some View {
        HStack {
            Button("Open Backup Folder") { if let d = s.dest.string { System.showInFinder(d) } }
                .disabled(!s.dest_exists.bool)
            Spacer()
            Button("Quit") { NSApp.terminate(nil) }
        }
        .buttonStyle(.plain).font(.system(size: 12)).foregroundStyle(.secondary)
        .padding(.horizontal, 4).padding(.top, 2)
    }

    // MARK: the card

    var cardName: String {
        let cards = s.cards.array
        guard let first = cards.first else { return "" }
        return first.name.str + (cards.count > 1 ? " +\(cards.count - 1)" : "")
    }

    @ViewBuilder var hero: some View {
        let job = s.job, r = job.result, p = job.progress
        let kind = job.kind.str, st = job.state.str
        VStack(alignment: .leading, spacing: 12) {
            if !s.dest.exists {
                heroTop("folder.badge.plus", "Choose a backup folder", "Where your photos and videos will go.")
                Button { pickBackup() } label: { Text("Choose Folder").frame(maxWidth: .infinity) }.primaryAction()
            } else if !s.dest_drive_connected.bool {
                heroTop("externaldrive.badge.exclamationmark", "\(driveName) isn't connected",
                        "Plug in your backup drive.", tone: .red)
            } else if s.cards.array.isEmpty {
                heroTop("sdcard", "Insert a memory card", "ShotLoft notices it by itself.", dim: true)
            } else if job.exists == false || (kind == "plan" && st == "running") {
                heroTop("sdcard.fill", cardName,
                        p.exists ? "Checking what's new · \(p.done.int) of \(p.total.int) files" : "Checking what's new…",
                        ring: p.exists ? p.done.double / max(p.total.double, 1) : nil, ringSpins: !p.exists)
            } else if st == "error" {
                heroTop("sdcard.fill", cardName, job.error.str, tone: .red)
                Button { Task { await engine.act("/api/reset"); model.replan() } } label: {
                    Text("Try Again").frame(maxWidth: .infinity) }.primaryAction()
            } else if st == "running" && kind == "import" {
                let f = p.done.double / max(p.total.double, 1)
                heroTop("sdcard.fill", cardName, p.exists ? "Copying \(p.files_done.int) of \(p.files_total.int) files\(timeLeft(p))" : "Starting…", ring: f)
                VStack(spacing: 5) {
                    ProgressView(value: f).tint(brand)
                    HStack { Text("\(human(p.done.double)) of \(human(p.total.double))"); Spacer(); Text("\(Int(f * 100))%") }
                        .font(.system(size: 11)).foregroundStyle(.secondary).monospacedDigit()
                }
            } else if st == "running" && kind == "verify" {
                let f = p.exists ? p.done.double / max(p.total.double, 1) : nil
                heroTop("checkmark.shield", cardName, "Checking every file, byte by byte", ring: f, ringSpins: f == nil)
            } else if kind == "plan" {
                if r.new_files.int == 0 {
                    heroTop("sdcard.fill", cardName, "Everything is backed up", tone: .green, badge: "checkmark.circle.fill")
                } else if !r.enough_space.bool {
                    heroTop("sdcard.fill", cardName, "Not enough space on the backup drive for \(human(r.needed_bytes.double))", tone: .red)
                } else {
                    heroTop("sdcard.fill", cardName, "\(counts(r.new_photos.int, r.new_videos.int, r.new_xml.int)) new · \(human(r.needed_bytes.double))")
                    Button { Task { await say(engine.act("/api/import")) } } label: {
                        Text("Back Up \(counts(r.new_photos.int, r.new_videos.int, r.new_xml.int))").frame(maxWidth: .infinity)
                    }.primaryAction()
                }
            } else if kind == "import" {
                let errs = r.errors.array.count
                heroTop("sdcard.fill", cardName,
                        errs > 0 ? "\(plural(errs, "file")) couldn't be copied"
                            : "Backed up \(counts(r.photos.int, r.videos.int, r.xml.int))\(r.seconds.double >= 1 ? " in " + duration(r.seconds.double) : "")",
                        tone: errs > 0 ? .red : .green, badge: errs > 0 ? nil : "checkmark.circle.fill")
            } else if kind == "verify" {
                let bad = r.cards.array.reduce(0) { $0 + $1.missing.array.count + $1.different.array.count }
                heroTop("checkmark.shield.fill", cardName,
                        bad > 0 ? "\(plural(bad, "file")) not safely backed up. Don't format yet." : "Safe to format in your camera",
                        tone: bad > 0 ? .red : .green, badge: bad > 0 ? nil : "checkmark.circle.fill")
            }
        }
        .padding(14)
        .surface(18)
    }

    enum Tone { case normal, green, red }

    func heroTop(_ symbol: String, _ title: String, _ subtitle: String, tone: Tone = .normal, dim: Bool = false,
                 badge: String? = nil, ring: Double? = nil, ringSpins: Bool = false) -> some View {
        HStack(spacing: 12) {
            Image(systemName: symbol)
                .font(.system(size: 21, weight: .medium))
                .symbolRenderingMode(.hierarchical)
                .foregroundStyle(dim ? AnyShapeStyle(.secondary) : AnyShapeStyle(brand))
                .frame(width: 46, height: 46)
                .background((dim ? Color.secondary : brand).opacity(0.14), in: RoundedRectangle(cornerRadius: 13, style: .continuous))
            VStack(alignment: .leading, spacing: 2) {
                Text(title).font(.system(size: 14.5, weight: .semibold)).lineLimit(1)
                HStack(spacing: 4) {
                    if let badge { Image(systemName: badge) }
                    Text(subtitle).lineLimit(2)
                }
                .font(.system(size: 12))
                .foregroundStyle(tone == .green ? AnyShapeStyle(Color.green) : tone == .red ? AnyShapeStyle(Color.red) : AnyShapeStyle(.secondary))
            }
            Spacer(minLength: 0)
            if ring != nil || ringSpins { Ring(fraction: ringSpins ? nil : ring) }
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
            RowGroup(title: "Card") {
                if kind != "verify" {
                    Row(symbol: "checkmark.shield.fill", title: "Check It's Safe to Format", detail: "Every file, byte by byte") {
                        Task { await say(engine.act("/api/verify")) }
                    }
                }
                if kind == "import", job.result.raw_jpg_pairs.int > 0 {
                    Row(symbol: "trash.fill", title: "Move \(plural(job.result.raw_jpg_pairs.int, "Extra JPG")) to the \(s.trash_name.str)",
                        detail: "Shot as RAW + JPG", tint: .orange) { Task { await trash() } }
                }
                Row(symbol: "eject.fill", title: "Eject Card", tint: .secondary) { Task { await eject() } }
            }
        }
    }

    // MARK: drive and tools

    var driveName: String {
        let d = s.dest_drive.str
        return d.isEmpty ? "This Mac" : (d as NSString).lastPathComponent
    }

    @ViewBuilder var drive: some View {
        if let dest = s.dest.string {
            let folder = dest.split(separator: "/").suffix(2).joined(separator: " / ")
            let free = s.free_bytes.exists ? " · \(human(s.free_bytes.double)) free" : ""
            RowGroup(title: "Backup Drive") {
                Row(symbol: s.dest_drive.exists ? "externaldrive.fill" : "internaldrive.fill", title: driveName,
                    detail: folder + (s.dest_drive_connected.bool ? free : " · not connected"), tint: .blue) {
                    if s.dest_exists.bool { System.showInFinder(dest) }
                }
            }
        }
    }

    var hdrDetail: String {
        let j = s.hdr_job
        if j.state.str == "running" { return j.kind.str == "merge" ? "Merging…" : "Looking for bracketed shots…" }
        return "Blend bracketed shots into one photo"
    }

    func updateBanner(_ latest: String) -> some View {
        HStack(spacing: 10) {
            Image(systemName: "arrow.down.circle.fill").font(.system(size: 18)).foregroundStyle(brand)
            VStack(alignment: .leading, spacing: 1) {
                Text("ShotLoft \(latest) is available").font(.system(size: 12.5, weight: .semibold))
                Text("Run the install line again to update.").font(.system(size: 11)).foregroundStyle(.secondary)
            }
            Spacer()
            Button("Copy Line") {
                NSPasteboard.general.clearContents()
                NSPasteboard.general.setString(s.update.line.str, forType: .string)
                note = ("Install line copied. Paste it into Terminal.", false)
            }.controlSize(.small)
        }
        .padding(10).surface(12)
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
            let results = r.results.array
            if let bad = results.first(where: { !$0.ejected.bool }) {
                note = ("Couldn't eject \((bad.card.str as NSString).lastPathComponent). Eject it in Finder.", true)
            } else if !results.isEmpty {
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
        dismiss()   // close the panel, then bring up the window
        openWindow(id: "hdr")
        NSApp.activate(ignoringOtherApps: true)
    }
}
