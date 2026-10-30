// Choosing what to back up, and tagging days: the Days page (every day of the card, ticked and
// tagged on its own) and a day's page (its files as small previews). Everything is chosen until
// you choose otherwise, so the panel's Back Up stays one click.

import SwiftUI

struct PlanFile: Identifiable {
    let id: Int
    let day: String              // "24Oct26"
    let kind: String             // photo, pair (RAW + JPG), video
    let name: String
    let files: Int
    let time: String
    let size: Double

    init(_ j: J) {
        id = j.id.int; day = j.day.str; kind = j.kind.str; name = j.name.str
        files = max(1, j.names.array.count); time = j.time.str; size = j.size.double
    }
    var isVideo: Bool { kind == "video" }
}

/// What to back up: the plan's files, which are chosen (nil: all of them), and their previews.
/// Kept by the app, and reset whenever the card is checked again.
@MainActor
final class ChoiceModel: ObservableObject {
    @Published var files: [PlanFile] = []
    @Published var chosen: Set<Int>?
    @Published var thumbs: [Int: NSImage] = [:]
    private var planID: Double = -1
    private var asked = Set<Int>()

    /// A new plan: forget the old choice and load its files.
    func sync(_ job: J, _ engine: Engine) {
        guard job.kind.str == "plan", job.state.str == "done", job.id.double != planID else { return }
        planID = job.id.double
        files = []; chosen = nil; thumbs = [:]; asked = []
        Task {
            guard let r = try? await engine.call("/api/plan/items") else { return }
            files = r.items.array.map(PlanFile.init)
        }
    }

    var all: Set<Int> { Set(files.map(\.id)) }
    var picked: Set<Int> { chosen ?? all }
    var everything: Bool { chosen == nil || chosen == all }

    func isOn(_ id: Int) -> Bool { picked.contains(id) }

    func set(_ ids: [Int], _ on: Bool) {
        var p = picked
        if on { p.formUnion(ids) } else { p.subtract(ids) }
        chosen = p == all ? nil : p
    }

    func toggle(_ id: Int) { set([id], !isOn(id)) }

    func only(_ keep: (PlanFile) -> Bool) {
        let p = Set(files.filter(keep).map(\.id))
        chosen = p == all ? nil : p
    }

    func count(_ ids: Set<Int>? = nil) -> Int { files.filter { (ids ?? picked).contains($0.id) }.reduce(0) { $0 + $1.files } }
    func bytes(_ ids: Set<Int>? = nil) -> Double { files.filter { (ids ?? picked).contains($0.id) }.reduce(0) { $0 + $1.size } }
    var totalFiles: Int { files.reduce(0) { $0 + $1.files } }

    func files(of day: String) -> [PlanFile] { files.filter { $0.day == day } }

    /// Previews for a day's photos, fetched once.
    func loadThumbs(_ ids: [Int], _ engine: Engine) {
        let want = ids.filter { !asked.contains($0) }
        guard !want.isEmpty else { return }
        asked.formUnion(want)
        Task {
            for chunk in stride(from: 0, to: want.count, by: 24).map({ Array(want[$0..<min($0 + 24, want.count)]) }) {
                guard let r = try? await engine.call("/api/plan/thumbs", ["ids": chunk]) else { continue }
                for id in chunk {
                    if let uri = r.thumbs[dynamicMember: String(id)].string, let img = Self.image(uri) { thumbs[id] = img }
                }
            }
        }
    }

    static func image(_ uri: String) -> NSImage? {
        guard let comma = uri.firstIndex(of: ","), let data = Data(base64Encoded: String(uri[uri.index(after: comma)...])) else { return nil }
        return NSImage(data: data)
    }
}

// MARK: small parts

enum Tick { case on, off, some }

struct TickMark: View {
    let tick: Tick
    @Environment(\.colorScheme) private var scheme
    var body: some View {
        let c = Ink(scheme: scheme)
        ZStack {
            switch tick {
            case .on:
                Circle().fill(c.ink)
                Image(systemName: "checkmark").font(.system(size: 9, weight: .heavy)).foregroundStyle(c.paper)
            case .some:
                Circle().fill(c.ink)
                Image(systemName: "minus").font(.system(size: 9, weight: .heavy)).foregroundStyle(c.paper)
            case .off:
                Circle().strokeBorder(Color.primary.opacity(0.35), lineWidth: 1.5)
            }
        }
        .frame(width: 18, height: 18)
        .animation(.smooth(duration: 0.2), value: tick)
    }
}

struct TagChip: View {
    let text: String
    var body: some View {
        HStack(spacing: 3) {
            Image(systemName: "tag.fill").font(.system(size: 8))
            Text(text).font(.system(size: 11, weight: .medium)).lineLimit(1)
        }
        .padding(.horizontal, 7).frame(height: 18)
        .background(Capsule().fill(Color.primary.opacity(0.1)))
    }
}

/// "+ Add tag": dashed, quiet, clearly optional.
struct AddTagButton: View {
    var short = false
    let action: () -> Void
    var body: some View {
        Button(action: action) {
            HStack(spacing: 3) {
                Image(systemName: "plus").font(.system(size: 8, weight: .bold))
                Text(short ? "Tag" : "Add tag").font(.system(size: 11, weight: .medium))
            }
            .foregroundStyle(.secondary)
            .padding(.horizontal, 7).frame(height: 18)
            .background(Capsule().strokeBorder(Color.primary.opacity(0.25), style: StrokeStyle(lineWidth: 1, dash: [2.5, 2])))
            .contentShape(Capsule())
        }
        .buttonStyle(PressStyle())
        .help("Name this day's folder, like \"24Oct26 - Birthday\"")
    }
}

/// Typing a day's tag, in place: the folder name as it will be, and recent tags to pick.
struct TagField: View {
    let day: String
    let start: String
    let recent: [String]
    let commit: (String) -> Void
    let cancel: () -> Void
    @State private var text = ""
    @FocusState private var focused: Bool

    var body: some View {
        VStack(spacing: 6) {
            HStack(spacing: 0) {
                Image(systemName: "folder.fill").font(.system(size: 10.5)).foregroundStyle(.tertiary).padding(.trailing, 6)
                Text("\(day) - ").font(.system(size: 12)).foregroundStyle(.secondary)
                TextField("Birthday, Ooty, Reunion…", text: $text)
                    .textFieldStyle(.plain).font(.system(size: 12, weight: .medium))
                    .focused($focused)
                    .onSubmit { commit(text) }
                    .onExitCommand { cancel() }
                Text("Return").font(.system(size: 10, weight: .medium)).foregroundStyle(.tertiary)
            }
            .padding(.horizontal, 10).frame(height: 26)
            .background(RoundedRectangle(cornerRadius: 7, style: .continuous).fill(Color.primary.opacity(0.07)))
            .overlay(RoundedRectangle(cornerRadius: 7, style: .continuous).strokeBorder(Color.primary.opacity(0.35), lineWidth: 1))
            let picks = suggestions
            if !picks.isEmpty {
                HStack(spacing: 5) {
                    ForEach(picks, id: \.self) { tag in
                        Button { commit(tag) } label: { TagChip(text: tag) }.buttonStyle(PressStyle())
                    }
                }
            }
        }
        .onAppear { text = start; focused = true }
    }

    /// Recent tags that start like what's typed (all of them when nothing is), at most three.
    var suggestions: [String] {
        let t = text.trimmingCharacters(in: .whitespaces).lowercased()
        return Array(recent.filter { t.isEmpty || ($0.lowercased().hasPrefix(t) && $0.lowercased() != t) }.prefix(3))
    }
}

/// A page's top: back, its title over a line, and an optional ⋯ menu.
struct PageHeader<Sub: View, Options: View>: View {
    let title: String
    let back: () -> Void
    @ViewBuilder var sub: Sub
    @ViewBuilder var options: Options

    var body: some View {
        HStack {
            Button(action: back) {
                Image(systemName: "chevron.left").font(.system(size: 12, weight: .bold))
                    .frame(width: 28, height: 28).background(Circle().fill(Color.primary.opacity(0.1))).contentShape(Circle())
            }
            .buttonStyle(PressStyle()).help("Back").accessibilityLabel("Back")
            Spacer()
            VStack(spacing: 2) {
                Text(title).font(.system(size: 13, weight: .semibold)).lineLimit(1)
                sub.font(.system(size: 11)).foregroundStyle(.secondary)
            }
            Spacer()
            options.frame(width: 28, height: 28)
        }
        .padding(.horizontal, Metrics.inset).padding(.top, 12).padding(.bottom, 8)
    }
}

struct OptionsButton: View {
    let items: () -> [System.MenuItem]
    var body: some View {
        Button { System.popUpMenu(items()) } label: {
            Image(systemName: "ellipsis").font(.system(size: 12, weight: .bold))
                .frame(width: 28, height: 28).background(Circle().fill(Color.primary.opacity(0.1))).contentShape(Circle())
        }
        .buttonStyle(PressStyle()).help("Options").accessibilityLabel("Options")
    }
}

/// "24 Oct 2026" for "24Oct26".
func dayTitle(_ key: String) -> String {
    guard key.count == 7, let d = Int(key.prefix(2)) else { return key }
    let mon = key.dropFirst(2).prefix(3), yy = key.suffix(2)
    return "\(d) \(mon) 20\(yy)"
}

/// "24–27 Oct", or "30 Oct – 2 Nov".
func dayRange(_ keys: [String]) -> String {
    guard let a = keys.first, let b = keys.last, a.count == 7, b.count == 7 else { return "" }
    let (d1, m1, d2, m2) = (Int(a.prefix(2)) ?? 0, a.dropFirst(2).prefix(3), Int(b.prefix(2)) ?? 0, b.dropFirst(2).prefix(3))
    return m1 == m2 ? "\(d1)–\(d2) \(m1)" : "\(d1) \(m1) – \(d2) \(m2)"
}

// MARK: the Days page

struct DaysPage: View {
    @EnvironmentObject var engine: Engine
    @ObservedObject var choice: ChoiceModel
    let back: () -> Void
    let open: (String) -> Void
    let tag: (String, String) -> Void
    let backUp: () -> Void
    @State private var editing: String?

    var s: J { engine.state }
    var days: [J] { s.job.kind.str == "plan" && s.job.state.str == "done" ? s.job.result.days.array : [] }

    var body: some View {
        VStack(spacing: 0) {
            PageHeader(title: days.count == 1 ? "Choose What to Back Up" : "\(days.count) Days to Back Up", back: back) {
                Text("\(choice.count().formatted()) of \(plural(choice.totalFiles, "new file")) · \(human(choice.bytes()))")
                    .monospacedDigit().contentTransition(.numericText())
            } options: {
                OptionsButton { menu }
            }
            Hairline()
            if days.isEmpty {
                Message(glyph: AnyView(BigBadge(mark: .quiet("sdcard"))), title: "Nothing to choose", sub: "Put a card in, and offcard checks what's new")
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                ScrollView {
                    VStack(spacing: 0) { ForEach(days, id: \.key.str) { row($0) } }.padding(.vertical, 4)
                }
                .frame(maxHeight: .infinity)
            }
            Hairline()
            SlotView(slot: slot).padding(.horizontal, Metrics.inset).padding(.top, 10).padding(.bottom, 14)
        }
    }

    var slot: Slot {
        let n = choice.count()
        return n == 0 ? .disabled("Back Up") : .ink("Back Up \(plural(n, "File"))", { backUp(); back() })
    }

    var menu: [System.MenuItem] {
        let photos = choice.files.filter { !$0.isVideo }, videos = choice.files.filter(\.isVideo)
        return [
            .init(title: "Select Everything", checked: choice.everything) { choice.chosen = nil },
            .init(title: "Select Nothing", checked: choice.picked.isEmpty) { choice.chosen = [] },
            .init(title: "Photos Only", detail: "\(photos.reduce(0) { $0 + $1.files })", enabled: !photos.isEmpty) { choice.only { !$0.isVideo } },
            .init(title: "Videos Only", detail: "\(videos.reduce(0) { $0 + $1.files })", enabled: !videos.isEmpty) { choice.only(\.isVideo) },
            .separator,
            .init(title: "Files left out stay on the card and show as new next time.", enabled: false) {},
        ]
    }

    func tick(_ ids: [Int]) -> Tick {
        let on = ids.filter(choice.isOn).count
        return on == 0 ? .off : on == ids.count ? .on : .some
    }

    func row(_ d: J) -> some View {
        let key = d.key.str, ids = d.ids.array.map(\.int), t = tick(ids)
        let mine = Set(ids).intersection(choice.picked)
        return HStack(spacing: 10) {
            Button { choice.set(ids, t != .on) } label: { TickMark(tick: t) }.buttonStyle(PressStyle())
                .accessibilityLabel(t == .on ? "Leave out \(dayTitle(key))" : "Back up \(dayTitle(key))")
            VStack(alignment: .leading, spacing: 3) {
                if editing == key {
                    TagField(day: key, start: d.tag.str, recent: s.recent_tags.strings,
                             commit: { tag(key, $0); editing = nil }, cancel: { editing = nil })
                } else {
                    HStack(spacing: 6) {
                        Text((d.folder.str as NSString).lastPathComponent).font(.system(size: 13, weight: .medium)).lineLimit(1)
                        if d.tag.str.isEmpty {
                            AddTagButton(short: true) { editing = key }
                        } else {
                            Button { editing = key } label: { Image(systemName: "pencil").font(.system(size: 10, weight: .semibold)).foregroundStyle(.tertiary) }
                                .buttonStyle(PressStyle()).help("Change this day's tag")
                        }
                    }
                }
                Text(detail(d, mine: mine, all: ids)).font(.system(size: 11)).monospacedDigit().foregroundStyle(.secondary).lineLimit(1)
            }
            Spacer(minLength: 6)
            Button { open(key) } label: {
                Image(systemName: "chevron.right").font(.system(size: 11, weight: .semibold)).foregroundStyle(.tertiary)
                    .frame(width: 24, height: 32).contentShape(Rectangle())
            }
            .buttonStyle(PressStyle()).help("Choose files from \(dayTitle(key))")
        }
        .padding(.horizontal, Metrics.inset).padding(.vertical, 7)
    }

    func detail(_ d: J, mine: Set<Int>, all: [Int]) -> String {
        if mine.isEmpty { return "\(plural(choice.count(Set(all)), "file")) · left for later" }
        let what = [d.photos.int > 0 ? plural(d.photos.int, "photo") : nil, d.videos.int > 0 ? plural(d.videos.int, "video") : nil]
            .compactMap { $0 }.joined(separator: " · ")
        if mine.count == all.count { return "\(what) · \(human(d.bytes.double))" }
        return "\(choice.count(mine)) of \(choice.count(Set(all))) · \(human(choice.bytes(mine)))"
    }
}

// MARK: a day's files

struct DayFilesPage: View {
    @EnvironmentObject var engine: Engine
    @ObservedObject var choice: ChoiceModel
    let day: String
    let back: () -> Void
    let backUp: () -> Void

    var s: J { engine.state }
    var tag: String { s.job.result.days.array.first { $0.key.str == day }?.tag.str ?? "" }

    var body: some View {
        let files = choice.files(of: day)
        let photos = files.filter { !$0.isVideo }, videos = files.filter(\.isVideo)
        VStack(spacing: 0) {
            PageHeader(title: dayTitle(day), back: back) {
                HStack(spacing: 6) {
                    if !tag.isEmpty { TagChip(text: tag) }
                    Text("\(files.filter { choice.isOn($0.id) }.reduce(0) { $0 + $1.files }) of \(files.reduce(0) { $0 + $1.files }) chosen")
                        .monospacedDigit().contentTransition(.numericText())
                }
            } options: {
                OptionsButton {
                    [.init(title: "Select All") { choice.set(files.map(\.id), true) },
                     .init(title: "Select None") { choice.set(files.map(\.id), false) }]
                }
            }
            Hairline()
            ScrollView {
                VStack(alignment: .leading, spacing: 8) {
                    if !photos.isEmpty { section("Photos", photos) }
                    if !videos.isEmpty { section("Videos", videos) }
                }
                .padding(.horizontal, Metrics.inset).padding(.vertical, 8)
            }
            .frame(maxHeight: .infinity)
            Hairline()
            SlotView(slot: choice.count() == 0 ? .disabled("Back Up") : .ink("Back Up \(plural(choice.count(), "File"))", { backUp(); back(); back() }))
                .padding(.horizontal, Metrics.inset).padding(.top, 10).padding(.bottom, 14)
        }
        .onAppear { choice.loadThumbs(photos.map(\.id), engine) }
    }

    func section(_ title: String, _ items: [PlanFile]) -> some View {
        let allOn = items.allSatisfy { choice.isOn($0.id) }
        return VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text("\(title) · \(items.count)").font(.system(size: 11, weight: .semibold)).foregroundStyle(.secondary)
                Spacer()
                Button(allOn ? "Select None" : "Select All") { choice.set(items.map(\.id), !allOn) }
                    .buttonStyle(.plain).font(.system(size: 11, weight: .medium)).foregroundStyle(.secondary)
            }
            LazyVGrid(columns: Array(repeating: GridItem(.fixed(75), spacing: 6), count: 4), spacing: 6) {
                ForEach(items) { tile($0) }
            }
        }
    }

    func tile(_ f: PlanFile) -> some View {
        let on = choice.isOn(f.id)
        return Button { choice.toggle(f.id) } label: {
            ZStack {
                if let img = choice.thumbs[f.id] {
                    Image(nsImage: img).resizable().aspectRatio(contentMode: .fill)
                } else {
                    Rectangle().fill(Color.primary.opacity(0.08))
                    Image(systemName: f.isVideo ? "video.fill" : "photo").font(.system(size: 16)).foregroundStyle(.tertiary)
                }
            }
            .frame(width: 75, height: 75)
            .clipShape(RoundedRectangle(cornerRadius: 7, style: .continuous))
            .opacity(on ? 1 : 0.45)
            .overlay(RoundedRectangle(cornerRadius: 7, style: .continuous).strokeBorder(on ? Color.primary : .clear, lineWidth: 2))
            .overlay(alignment: .topTrailing) { TickMark(tick: on ? .on : .off).padding(5) }
            .overlay(alignment: .bottomLeading) {
                let badge = f.kind == "pair" ? "RAW+JPG" : f.isVideo ? f.time.prefix(5).description : nil
                if let badge {
                    HStack(spacing: 2) {
                        if f.isVideo { Image(systemName: "play.fill").font(.system(size: 6)) }
                        Text(badge).font(.system(size: 7.5, weight: .heavy))
                    }
                    .foregroundStyle(.white).padding(.horizontal, 4).frame(height: 13)
                    .background(Capsule().fill(.black.opacity(0.55))).padding(5)
                }
            }
        }
        .buttonStyle(PressStyle())
        .help("\(f.name) · \(f.time)")
        .accessibilityLabel("\(f.name), \(f.time), \(on ? "chosen" : "left out")")
    }
}
