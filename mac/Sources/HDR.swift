// HDR Merge, inside the popup: a page the panel slides to. The bracketed sets in a folder (and its
// subfolders) as a list grouped by day — a bracket glyph for each, never the photos — new sets
// chosen, and one button that says what it does: "Merge 3 Sets", then "Show in Finder".

import SwiftUI

struct BracketSet: Identifiable {
    let id: Int
    let folder: String, names: [String], biases: [Double], date: String, time: String, done: Bool
    let output: String

    var evs: String {
        biases.map { $0 > 0 ? "+\(fmt($0))" : $0 < 0 ? "−\(fmt(-$0))" : "0" }.joined(separator: " · ") + " EV"
    }
    private func fmt(_ v: Double) -> String { v == v.rounded() ? String(Int(v)) : String(v) }

    init(_ j: J) {
        id = j.id.int; folder = j.folder.str; names = j.names.strings
        biases = j.biases.array.map(\.double); date = j.date.str; time = j.time.str; done = j.done.bool
        output = j.output.str
    }
}

/// HDR Merge's state, kept by the app so it survives the popup closing (a merge keeps going).
@MainActor
final class HDRModel: ObservableObject {
    @Published var sets: [BracketSet]?
    @Published var selected = Set<Int>()
    @Published var tiff = false
    @Published var merging: [Int] = []            // the sets of the running (or last) merge, in order
    @Published var failed: [String: String] = [:] // output name → why it couldn't be merged
    @Published var lastMerged: Int?
    @Published var note: String?
    var mergeStart = Date()
    private var seenJob: Double = -1

    func open(_ engine: Engine) {
        let s = engine.state, job = s.hdr_job
        guard s.hdr_folder.exists, s.hdr_folder_exists.bool else { return }
        if sets == nil {
            if job.state.str == "running" { return }
            if job.exists && job.state.str == "done" { load(engine) } else { scan(engine) }
        }
    }

    func folderChanged(_ engine: Engine) {
        sets = nil; selected = []; merging = []; failed = [:]; lastMerged = nil
        open(engine)
    }

    /// A job finished: load the sets again (the merged ones are marked done), note any failures.
    func jobChanged(_ engine: Engine) {
        let job = engine.state.hdr_job
        guard job.exists, job.state.str != "running", job.id.double != seenJob else { return }
        seenJob = job.id.double
        if job.state.str == "error" { note = job.error.str }
        if job.kind.str == "merge", job.result.exists {
            failed = Dictionary(uniqueKeysWithValues: job.result.failed.array.map { ($0.file.str, $0.error.str) })
        }
        load(engine)
    }

    func load(_ engine: Engine) {
        Task {
            guard let r = try? await engine.call("/api/hdr/sets") else { return }
            guard r.sets.exists else { scan(engine); return }
            let list = r.sets.array.map(BracketSet.init)
            let first = sets == nil
            sets = list
            if first { selected = Set(list.filter { !$0.done }.map(\.id)) }
            else { selected = selected.filter { id in list.first { $0.id == id }.map { !$0.done } ?? false } }
            if let done = merging.last(where: { id in list.first { $0.id == id }?.done == true }) { lastMerged = done }
        }
    }

    func scan(_ engine: Engine) {
        guard engine.state.hdr_job.state.str != "running" else { return }
        note = nil
        Task { if let e = await engine.act("/api/hdr/scan") { note = e } }
    }

    func merge(_ engine: Engine) {
        let ids = Array(selected).sorted()
        guard !ids.isEmpty else { return }
        note = nil; failed = [:]; lastMerged = nil
        merging = ids; mergeStart = Date()
        Task { if let e = await engine.act("/api/hdr/merge", ["ids": ids, "tiff": tiff]) { note = e; merging = [] } }
    }

    func setFolder(_ engine: Engine, _ path: String) {
        note = nil
        Task { if let e = await engine.act("/api/hdr/folder", ["path": path]) { note = e } }
    }

    func reveal(_ engine: Engine, _ id: Int) {
        Task { if let e = await engine.act("/api/reveal", ["id": id]) { note = e } }
    }

    /// After a merge: clear its marks so the list is back to choosing.
    func finish() { merging = []; failed = [:]; lastMerged = nil; note = nil }
}

/// The bracket glyph: three tiles, dark to light — a set, without showing the photo.
struct BracketGlyph: View {
    var size: CGFloat = 28
    var inked = false
    @Environment(\.colorScheme) private var scheme
    var body: some View {
        let c = Ink(scheme: scheme)
        ZStack {
            Circle().fill(inked ? c.ink : Color.primary.opacity(0.1))
            HStack(spacing: -size * 0.1) {
                ForEach(0..<3, id: \.self) { i in
                    RoundedRectangle(cornerRadius: size * 0.07, style: .continuous)
                        .fill((inked ? c.paper : Color.primary).opacity([0.3, 0.6, 0.95][i]))
                        .frame(width: size * 0.26, height: size * 0.34)
                        .overlay(RoundedRectangle(cornerRadius: size * 0.07, style: .continuous)
                            .strokeBorder(Color.primary.opacity(0.15), lineWidth: 0.5))
                        .offset(y: CGFloat(i - 1) * -size * 0.03)
                }
            }
        }
        .frame(width: size, height: size)
        .accessibilityHidden(true)
    }
}

/// The trailing pick: an inked check when chosen, an empty ring when not.
struct Pick: View {
    let on: Bool
    @Environment(\.colorScheme) private var scheme
    var body: some View {
        let c = Ink(scheme: scheme)
        ZStack {
            if on {
                Circle().fill(c.ink)
                Image(systemName: "checkmark").font(.system(size: 9, weight: .heavy)).foregroundStyle(c.paper)
            } else {
                Circle().strokeBorder(Color.primary.opacity(0.35), lineWidth: 1.5)
            }
        }
        .frame(width: 18, height: 18)
        .animation(.smooth(duration: 0.2), value: on)
    }
}

struct MiniRing: View {
    let p: Double
    @Environment(\.colorScheme) private var scheme
    var body: some View {
        ZStack {
            Circle().stroke(Color.primary.opacity(0.15), lineWidth: 2)
            Circle().trim(from: 0, to: max(0.02, p))
                .stroke(Ink(scheme: scheme).ink, style: StrokeStyle(lineWidth: 2, lineCap: .round)).rotationEffect(.degrees(-90))
        }
        .frame(width: 18, height: 18)
        .animation(.linear(duration: 0.55), value: p)
    }
}

// MARK: the page

struct HDRPage: View {
    @EnvironmentObject var engine: Engine
    @ObservedObject var model: HDRModel
    let back: () -> Void

    var s: J { engine.state }
    var job: J { s.hdr_job }
    var busy: Bool { job.state.str == "running" }
    var isMerging: Bool { busy && job.kind.str == "merge" }
    var folderName: String { (s.hdr_folder.str as NSString).lastPathComponent }

    var body: some View {
        VStack(spacing: 0) {
            header
            Hairline()
            content.frame(maxWidth: .infinity, maxHeight: .infinity)
            Hairline()
            SlotView(slot: slot).padding(.horizontal, Metrics.inset).padding(.top, 10).padding(.bottom, 14)
        }
        .onAppear { model.open(engine) }
        .onChange(of: job.json) { model.jobChanged(engine) }
        .onChange(of: s.hdr_folder.str) { model.folderChanged(engine) }
    }

    // MARK: header: back, the title over its folder, options

    var header: some View {
        HStack {
            Button(action: back) {
                Image(systemName: "chevron.left").font(.system(size: 12, weight: .bold))
                    .frame(width: 28, height: 28).background(Circle().fill(Color.primary.opacity(0.1)))
                    .contentShape(Circle())
            }
            .buttonStyle(PressStyle()).help("Back").accessibilityLabel("Back")
            Spacer()
            VStack(spacing: 1) {
                Text("HDR Merge").font(.system(size: 13, weight: .semibold))
                folderMenu
            }
            Spacer()
            optionsMenu
        }
        .padding(.horizontal, Metrics.inset).padding(.top, 12).padding(.bottom, 8)
    }

    var folderMenu: some View {
        Menu {
            Button("Choose Another Folder…") { chooseFolder() }
            if let dest = s.dest.string, dest != s.hdr_folder.str { Button("Use Backup Folder") { model.setFolder(engine, dest) } }
            Divider()
            Button("Show in Finder") { if let f = s.hdr_folder.string { System.showInFinder(f) } }
                .disabled(!s.hdr_folder_exists.bool)
        } label: {
            Text(s.hdr_folder.exists ? "in \(folderName) \(Image(systemName: "chevron.up.chevron.down"))"
                                     : "no folder yet \(Image(systemName: "chevron.up.chevron.down"))")
                .font(.system(size: 11)).foregroundStyle(.secondary)
        }
        .menuStyle(.borderlessButton).menuIndicator(.hidden).fixedSize()
        .disabled(busy)
    }

    var optionsMenu: some View {
        Menu {
            Button("Select New Sets") { model.selected = Set((model.sets ?? []).filter { !$0.done }.map(\.id)) }
            Button("Select All") { model.selected = Set((model.sets ?? []).map(\.id)) }
            Button("Select None") { model.selected = [] }
            Divider()
            Toggle("Also Save a 16-bit TIFF", isOn: $model.tiff)
            Divider()
            Button("Look Again") { model.sets = nil; model.scan(engine) }.disabled(busy || !s.hdr_folder_exists.bool)
        } label: {
            Image(systemName: "ellipsis").font(.system(size: 12, weight: .bold))
                .frame(width: 28, height: 28).background(Circle().fill(Color.primary.opacity(0.1)))
        }
        .menuStyle(.borderlessButton).menuIndicator(.hidden).fixedSize()
        .disabled(isMerging)
        .help("Options").accessibilityLabel("Options")
    }

    // MARK: the list, or a message in its place

    @ViewBuilder var content: some View {
        if let missing = s.hdr_missing.string {
            Message(glyph: AnyView(BigBadge(mark: .alert("exclamationmark"))), title: "HDR Merge isn't available", sub: missing)
        } else if !s.hdr_folder.exists {
            Message(glyph: AnyView(BracketGlyph(size: 40)), title: "Choose a folder",
                    sub: "offcard finds the bracketed shots in it,\nand in every folder inside it.")
        } else if !s.hdr_folder_exists.bool {
            Message(glyph: AnyView(BigBadge(mark: .alert("exclamationmark"))), title: "\(place(s.hdr_folder.str).drive) isn't connected",
                    sub: "Plug it in to see its bracketed shots", bad: true)
        } else if busy && job.kind.str == "scan" {
            let p = job.progress
            Message(glyph: AnyView(BigBadge(mark: .spinner)), title: "Looking for bracketed shots…",
                    sub: p.stage.str == "Making previews" ? "Almost done"
                        : p.exists ? "Reading \(p.done.int.formatted()) of \(p.total.int.formatted()) photos in \(folderName)" : "In \(folderName)")
        } else if let sets = model.sets {
            if sets.isEmpty {
                Message(glyph: AnyView(BracketGlyph(size: 40)), title: "No bracketed shots in \(folderName)",
                        sub: "Shoot with Continuous Bracket (BRK C) in RAW,\nthen back the card up.")
            } else {
                list(sets)
            }
        } else {
            Message(glyph: AnyView(BigBadge(mark: .spinner)), title: "Looking for bracketed shots…", sub: "In \(folderName)")
        }
    }

    func list(_ sets: [BracketSet]) -> some View {
        ScrollView {
            LazyVStack(spacing: 0, pinnedViews: [.sectionHeaders]) {
                ForEach(days(sets), id: \.0) { day, items in
                    Section {
                        ForEach(items) { row($0) }
                    } header: {
                        Text(day).font(.system(size: 11, weight: .semibold)).foregroundStyle(.secondary)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .padding(.horizontal, Metrics.inset).padding(.top, 8).padding(.bottom, 2)
                            .background(.background.opacity(0.001))
                    }
                }
            }
            .padding(.bottom, 4)
        }
        .scrollIndicators(.automatic)
    }

    enum RowState: Equatable { case pick(Bool), merged, waiting, merging(Double), failed(String) }

    func state(of set: BracketSet) -> RowState {
        if let why = model.failed[set.output] { return .failed(why) }
        if isMerging, let k = model.merging.firstIndex(of: set.id) {
            let at = job.progress.done.double
            if Double(k) + 1 <= at || set.done { return .merged }
            if Double(k) <= at { return .merging(at - Double(k)) }
            return .waiting
        }
        if set.done { return .merged }
        return .pick(model.selected.contains(set.id))
    }

    func row(_ set: BracketSet) -> some View {
        let st = state(of: set)
        return Button { if case .pick = st { toggle(set.id) } } label: {
            HStack(spacing: 10) {
                BracketGlyph(inked: st == .merged)
                VStack(alignment: .leading, spacing: 1) {
                    Text("\(set.time) · \(plural(set.names.count, "shot"))").font(.system(size: 13, weight: .medium))
                    if case .failed(let why) = st {
                        Text("Couldn't merge: \(why)").font(.system(size: 11)).foregroundStyle(.red).lineLimit(1)
                    } else {
                        Text(set.evs).font(.system(size: 11)).foregroundStyle(.secondary).lineLimit(1)
                    }
                }
                Spacer(minLength: 6)
                switch st {
                case .pick(let on): Pick(on: on)
                case .merged: Text("Merged").font(.system(size: 11)).foregroundStyle(.secondary)
                case .waiting: Text("Waiting").font(.system(size: 11)).foregroundStyle(.tertiary)
                case .merging(let p):
                    HStack(spacing: 6) {
                        Text("\(Int(p * 100))%").font(.system(size: 11)).monospacedDigit().foregroundStyle(.secondary)
                            .contentTransition(.numericText(value: p))
                        MiniRing(p: p)
                    }
                case .failed: Image(systemName: "exclamationmark.circle.fill").foregroundStyle(.red)
                }
            }
            .padding(.horizontal, Metrics.inset).frame(height: 44)
        }
        .buttonStyle(MenuRowStyle())
        .contextMenu {
            if case .pick(let on) = st { Button(on ? "Deselect" : "Select") { toggle(set.id) } }
            if set.done { Button("Show HDR in Finder") { model.reveal(engine, set.id) } }
        }
        .accessibilityLabel("\(set.date), \(set.time), \(plural(set.names.count, "shot")), \(set.evs)")
    }

    func toggle(_ id: Int) {
        if model.selected.contains(id) { model.selected.remove(id) } else { model.selected.insert(id) }
    }

    func days(_ sets: [BracketSet]) -> [(String, [BracketSet])] {
        var order: [String] = [], by: [String: [BracketSet]] = [:]
        for set in sets {
            if by[set.date] == nil { order.append(set.date) }
            by[set.date, default: []].append(set)
        }
        return order.map { ($0, by[$0]!) }
    }

    // MARK: the one button

    var slot: Slot {
        if let note = model.note, !busy { return .text(note) }
        if s.hdr_missing.exists { return .disabled("Merge") }
        if !s.hdr_folder.exists {
            if let dest = s.dest.string { return .ink("Use Backup Folder", { model.setFolder(engine, dest) }) }
            return .ink("Choose Folder…", chooseFolder)
        }
        if !s.hdr_folder_exists.bool { return .quiet("Choose Another Folder…", chooseFolder) }
        if busy && job.kind.str == "scan" { return .disabled("Merge") }
        if isMerging {
            let p = job.progress, at = p.done.double, total = max(p.total.double, 1)
            let n = min(Int(at) + 1, p.total.int)
            var line = "Merging \(n) of \(p.total.int)"
            let t = Date().timeIntervalSince(model.mergeStart)
            if at > 0.15, t > 3 {
                let left = t / at * (total - at)
                line += left < 50 ? " · less than a minute left" : " · about \(plural(Int((left / 60).rounded(.up)), "minute")) left"
            }
            return .text(line)
        }
        guard let sets = model.sets, !sets.isEmpty else {
            return model.sets == nil ? .disabled("Merge") : .quiet("Choose Another Folder…", chooseFolder)
        }
        if !model.merging.isEmpty {        // a merge just finished
            let reveal = model.lastMerged
            if !model.failed.isEmpty {
                return .inkPair("Retry", retry, reveal == nil ? "Done" : "Show", {
                    if let reveal { model.reveal(engine, reveal) } else { model.finish() }
                })
            }
            return .inkPair("Show in Finder", { if let reveal { model.reveal(engine, reveal) } },
                            "Done", { model.finish(); back() })
        }
        let n = model.selected.count
        if n == 0 { return sets.allSatisfy(\.done) ? .text("Every set here is merged") : .disabled("Merge") }
        return .ink("Merge \(plural(n, "Set"))", { model.merge(engine) })
    }

    func retry() {
        let again = (model.sets ?? []).filter { model.failed[$0.output] != nil }.map(\.id)
        model.selected = Set(again)
        model.merge(engine)
    }

    func chooseFolder() {
        if let p = System.chooseFolder("Choose a folder with bracketed shots", startingAt: s.hdr_folder.string ?? s.dest.string) {
            model.setFolder(engine, p)
        }
    }
}

/// A centred message where the list would be: a glyph, a line, and a quieter line.
struct Message: View {
    let glyph: AnyView
    let title: String
    let sub: String
    var bad = false
    var body: some View {
        VStack(spacing: 8) {
            glyph
            Text(title).font(.system(size: 13, weight: .semibold)).multilineTextAlignment(.center)
            Text(sub).font(.system(size: 11)).foregroundStyle(bad ? AnyShapeStyle(Color.red) : AnyShapeStyle(.secondary))
                .multilineTextAlignment(.center)
        }
        .padding(.horizontal, Metrics.inset)
    }
}
