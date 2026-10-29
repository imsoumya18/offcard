// HDR Merge: every bracketed set in a folder (subfolders too) as a photo grid, in the manner of
// Photos: grouped by day, selected with a check, the actions in the toolbar.

import SwiftUI

struct BracketSet: Identifiable {
    let id: Int
    let folder: String, names: [String], biases: [Double], date: String, time: String, done: Bool
    let thumb: NSImage?

    var title: String {
        guard let first = names.first?.replacingOccurrences(of: ".ARW", with: "", options: .caseInsensitive) else { return "" }
        guard names.count > 1, let last = names.last?.replacingOccurrences(of: ".ARW", with: "", options: .caseInsensitive)
        else { return first }
        return "\(first)–\(last.drop(while: { !$0.isNumber }))"
    }
    var evs: String {
        biases.map { $0 > 0 ? "+\(fmt($0))" : $0 < 0 ? "−\(fmt(-$0))" : "0" }.joined(separator: " ") + " EV"
    }
    private func fmt(_ v: Double) -> String { v == v.rounded() ? String(Int(v)) : String(v) }

    init(_ j: J) {
        id = j.id.int; folder = j.folder.str; names = j.names.strings
        biases = j.biases.array.map(\.double); date = j.date.str; time = j.time.str; done = j.done.bool
        thumb = image(fromDataURI: j.thumb.string)
    }
}

struct HDRView: View {
    @EnvironmentObject var engine: Engine
    @State private var sets: [BracketSet]?
    @State private var selected = Set<Int>()
    @State private var tiff = false
    @State private var seenJob: Double = -1
    @State private var status: String?
    @State private var failure: String?

    var s: J { engine.state }
    var job: J { s.hdr_job }
    var busy: Bool { job.state.str == "running" }
    var merging: Bool { busy && job.kind.str == "merge" }

    var body: some View {
        content
            .frame(minWidth: 640, minHeight: 460)
            .navigationTitle("HDR Merge")
            .navigationSubtitle(subtitle)
            .toolbar { toolbar }
            .safeAreaInset(edge: .top, spacing: 0) {
                if merging {
                    ProgressView(value: job.progress.done.double / max(job.progress.total.double, 1))
                        .progressViewStyle(.linear).tint(brand).frame(height: 3).padding(.horizontal, 0)
                }
            }
            .alert("Couldn't merge", isPresented: Binding(get: { failure != nil }, set: { if !$0 { failure = nil } })) {
                Button("OK") { failure = nil }
            } message: { Text(failure ?? "") }
            .onAppear { start() }
            .onChange(of: job.id.double) { _, _ in jobChanged() }
            .onChange(of: job.state.str) { _, _ in jobChanged() }
            .onChange(of: s.hdr_folder.str) { _, _ in sets = nil; scan() }
    }

    var subtitle: String {
        let folder = (s.hdr_folder.str as NSString).lastPathComponent
        if merging {
            let p = job.progress
            return "Merging \(p.name.str.replacingOccurrences(of: "_HDR.jpg", with: "")) · \(min(Int(p.done.double) + 1, p.total.int)) of \(p.total.int)"
        }
        if busy { return "Looking in \(folder)…" }
        if let status { return status }
        guard let sets else { return folder }
        let done = sets.filter(\.done).count
        return "\(folder) · \(plural(sets.count, "set"))\(done > 0 ? ", \(done) merged" : "")"
    }

    // MARK: toolbar

    @ToolbarContentBuilder var toolbar: some ToolbarContent {
        ToolbarItemGroup(placement: .primaryAction) {
            Button { chooseFolder() } label: { Label("Choose Folder", systemImage: "folder") }
                .help("Choose the folder to look in")
            Button { scan() } label: { Label("Look Again", systemImage: "arrow.clockwise") }
                .disabled(busy || !s.hdr_folder.exists).help("Look for bracketed shots again")
            Menu {
                Toggle("Also Save a 16-bit TIFF", isOn: $tiff)
                Divider()
                Button("Select All") { selected = Set((sets ?? []).map(\.id)) }
                Button("Select New") { selected = Set((sets ?? []).filter { !$0.done }.map(\.id)) }
                Button("Select None") { selected = [] }
            } label: { Label("Options", systemImage: "ellipsis.circle") }
            Button { merge() } label: {
                Text(selected.isEmpty ? "Merge" : "Merge \(plural(selected.count, "Set"))")
            }
            .buttonStyle(.borderedProminent).tint(brand)
            .disabled(selected.isEmpty || busy)
            .keyboardShortcut(.defaultAction)
        }
    }

    // MARK: content

    @ViewBuilder var content: some View {
        if let missing = s.hdr_missing.string {
            ContentUnavailableView("HDR Merge Isn't Available", systemImage: "exclamationmark.triangle", description: Text(missing))
        } else if !s.hdr_folder.exists {
            ContentUnavailableView {
                Label("Choose a Folder", systemImage: "square.stack.3d.up")
            } description: {
                Text("ShotLoft finds the bracketed shots in it, and in every folder inside it.")
            } actions: {
                if let dest = s.dest.string {
                    Button("Use Backup Folder") { setFolder(dest) }.mainAction()
                }
                Button("Choose Folder…") { chooseFolder() }
            }
        } else if !s.hdr_folder_exists.bool {
            ContentUnavailableView("Folder Not Found", systemImage: "externaldrive.badge.questionmark",
                                   description: Text("Is the drive with \((s.hdr_folder.str as NSString).lastPathComponent) connected?"))
        } else if busy && job.kind.str == "scan" {
            let p = job.progress
            VStack(spacing: 10) {
                ProgressView(value: p.exists ? p.done.double / max(p.total.double, 1) : nil).frame(width: 240).tint(brand)
                Text(p.stage.str == "Making previews" ? "Making previews" : "Reading \(p.done.int.formatted()) of \(p.total.int.formatted()) photos")
                    .font(.callout).foregroundStyle(.secondary).monospacedDigit()
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        } else if let sets {
            if sets.isEmpty {
                ContentUnavailableView("No Bracketed Shots", systemImage: "camera.aperture",
                                       description: Text("Shoot with exposure bracketing (BRK C) in RAW, then look again."))
            } else {
                grid(sets)
            }
        } else {
            ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity)
        }
    }

    func grid(_ sets: [BracketSet]) -> some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 18, pinnedViews: [.sectionHeaders]) {
                ForEach(days(sets), id: \.0) { day, items in
                    Section {
                        LazyVGrid(columns: [GridItem(.adaptive(minimum: 190, maximum: 320), spacing: 6)], spacing: 14) {
                            ForEach(items) { tile($0) }
                        }
                    } header: {
                        HStack(alignment: .firstTextBaseline) {
                            Text(day).font(.system(size: 17, weight: .bold))
                            Text(places(items)).font(.system(size: 12)).foregroundStyle(.secondary).lineLimit(1)
                            Spacer()
                        }
                        .padding(.vertical, 8)
                        .background(.background.opacity(0.92))
                    }
                }
            }
            .padding(.horizontal, 18).padding(.bottom, 18)
        }
    }

    func days(_ sets: [BracketSet]) -> [(String, [BracketSet])] {
        var order: [String] = [], by: [String: [BracketSet]] = [:]
        for set in sets {
            if by[set.date] == nil { order.append(set.date) }
            by[set.date, default: []].append(set)
        }
        return order.map { ($0, by[$0]!) }
    }

    func places(_ items: [BracketSet]) -> String {
        Array(Set(items.map { $0.folder.replacingOccurrences(of: "/", with: " › ") })).sorted().joined(separator: ", ")
    }

    func tile(_ set: BracketSet) -> some View {
        let on = selected.contains(set.id)
        return VStack(alignment: .leading, spacing: 5) {
            ZStack {
                if let img = set.thumb {
                    Image(nsImage: img).resizable().aspectRatio(contentMode: .fill)
                } else {
                    Rectangle().fill(.fill.tertiary).overlay(Image(systemName: "photo").foregroundStyle(.tertiary))
                }
            }
            .frame(minWidth: 0, maxWidth: .infinity).aspectRatio(3 / 2, contentMode: .fit)
            .clipShape(RoundedRectangle(cornerRadius: 6, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 6, style: .continuous).strokeBorder(brand, lineWidth: on ? 3 : 0))
            .overlay(alignment: .bottomTrailing) {
                if on {
                    Image(systemName: "checkmark.circle.fill").font(.system(size: 20))
                        .symbolRenderingMode(.palette).foregroundStyle(.white, brand)
                        .background(Circle().fill(.white).padding(3)).padding(7)
                }
            }
            .overlay(alignment: .topLeading) {
                if set.done {
                    Text("HDR").font(.system(size: 10, weight: .heavy)).tracking(0.5)
                        .padding(.horizontal, 6).padding(.vertical, 2.5)
                        .background(.ultraThinMaterial, in: Capsule()).padding(7)
                }
            }
            VStack(alignment: .leading, spacing: 0) {
                Text("\(set.time) · \(set.title)").font(.system(size: 11.5, weight: .medium)).lineLimit(1)
                Text("\(set.names.count) shots · \(set.evs)").font(.system(size: 11)).foregroundStyle(.secondary).lineLimit(1)
            }
            .padding(.horizontal, 2)
        }
        .contentShape(Rectangle())
        .onTapGesture { toggle(set.id) }
        .contextMenu {
            Button(on ? "Deselect" : "Select") { toggle(set.id) }
            if set.done {
                Button("Show HDR in Finder") { Task { await say(engine.act("/api/reveal", ["id": set.id])) } }
            }
        }
    }

    func toggle(_ id: Int) {
        if selected.contains(id) { selected.remove(id) } else { selected.insert(id) }
    }

    // MARK: talking to the engine

    func start() {
        if s.hdr_folder.exists && sets == nil {
            if job.state.str == "done" { load() } else if !busy { scan() }
        }
    }

    func chooseFolder() {
        if let p = System.chooseFolder("Choose a folder with bracketed shots", startingAt: s.hdr_folder.string ?? s.dest.string) {
            setFolder(p)
        }
    }

    func setFolder(_ path: String) {
        status = nil
        Task { await say(engine.act("/api/hdr/folder", ["path": path])) }
    }

    func scan() {
        guard s.hdr_folder.exists, !busy else { return }
        status = nil
        Task { await say(engine.act("/api/hdr/scan")) }
    }

    func merge() {
        status = nil
        Task { await say(engine.act("/api/hdr/merge", ["ids": Array(selected).sorted(), "tiff": tiff])) }
    }

    func jobChanged() {
        guard job.state.str != "running", job.id.double != seenJob else { return }
        seenJob = job.id.double
        if job.state.str == "error" { failure = job.error.str; return }
        if job.kind.str == "merge", job.result.exists {
            let merged = job.result.merged.int, failed = job.result.failed.array
            if !failed.isEmpty {
                failure = "\(plural(failed.count, "set")) couldn't be merged. \(failed[0].error.str)"
            }
            if merged > 0 { status = "Saved \(plural(merged, "HDR photo")) in the day's HDR folder" }
        }
        load()
    }

    func load() {
        Task {
            guard let r = try? await engine.call("/api/hdr/sets") else { return }
            let list = r.sets.array.map(BracketSet.init)
            let first = sets == nil
            sets = r.sets.exists ? list : nil
            if first || job.kind.str == "merge" { selected = Set(list.filter { !$0.done }.map(\.id)) }
            if !r.sets.exists && !busy { scan() }
        }
    }

    func say(_ error: String?) async {
        if let error { failure = error }
    }
}
