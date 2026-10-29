// HDR Merge: choose a folder, see every bracketed set found in it (subfolders too), merge them.

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
        biases.map { $0 > 0 ? "+\(fmt($0))" : $0 < 0 ? "−\(fmt(-$0))" : "0" }.joined(separator: ", ") + " EV"
    }
    private func fmt(_ v: Double) -> String { v == v.rounded() ? String(Int(v)) : String(v) }

    init(_ j: J) {
        id = j.id.int; folder = j.folder.str; names = j.names.strings
        biases = j.biases.array.map(\.double); date = j.date.str; time = j.time.str; done = j.done.bool
        if let uri = j.thumb.string, let comma = uri.firstIndex(of: ","),
           let data = Data(base64Encoded: String(uri[uri.index(after: comma)...])) {
            thumb = NSImage(data: data)
        } else { thumb = nil }
    }
}

struct HDRView: View {
    @EnvironmentObject var engine: Engine
    @State private var sets: [BracketSet]?
    @State private var selected = Set<Int>()
    @State private var tiff = false
    @State private var seenJob: Double = -1
    @State private var note: (text: String, bad: Bool)?

    var s: J { engine.state }
    var job: J { s.hdr_job }
    var busy: Bool { job.state.str == "running" }

    var body: some View {
        VStack(spacing: 0) {
            header
            Divider().opacity(0.5)
            content
            if sets?.isEmpty == false || busy { bottomBar }
        }
        .frame(minWidth: 560, minHeight: 480)
        .background(.background.opacity(0.0001))
        .onAppear { start() }
        .onChange(of: job.id.double) { _, _ in jobChanged() }
        .onChange(of: job.state.str) { _, _ in jobChanged() }
        .onChange(of: s.hdr_folder.str) { _, _ in sets = nil; scan() }
    }

    // MARK: folder

    var header: some View {
        HStack(spacing: 12) {
            Image(systemName: "folder.fill").font(.system(size: 18)).foregroundStyle(brand)
                .frame(width: 38, height: 38).background(brand.opacity(0.14), in: RoundedRectangle(cornerRadius: 10, style: .continuous))
            VStack(alignment: .leading, spacing: 1) {
                if let folder = s.hdr_folder.string {
                    Text((folder as NSString).lastPathComponent).font(.system(size: 14, weight: .semibold))
                    Text(s.hdr_folder_exists.bool ? "\(folder) · with all its subfolders" : "Not found. Is its drive connected?")
                        .font(.system(size: 11.5)).foregroundStyle(s.hdr_folder_exists.bool ? .secondary : Color.red)
                        .lineLimit(1).truncationMode(.middle)
                } else {
                    Text("Choose a folder with bracketed shots").font(.system(size: 14, weight: .semibold))
                    Text("Your backup folder works: every folder inside it is searched.")
                        .font(.system(size: 11.5)).foregroundStyle(.secondary)
                }
            }
            Spacer()
            if s.hdr_folder.string == nil, let dest = s.dest.string {
                Button("Use Backup Folder") { setFolder(dest) }
            }
            Button(s.hdr_folder.exists ? "Change…" : "Choose…") {
                if let p = System.chooseFolder("Choose a folder with bracketed shots", startingAt: s.hdr_folder.string ?? s.dest.string) {
                    setFolder(p)
                }
            }
            .keyboardShortcut("o")
        }
        .padding(.horizontal, 18).padding(.vertical, 14)
    }

    // MARK: the sets

    @ViewBuilder var content: some View {
        if let missing = s.hdr_missing.string {
            placeholder("exclamationmark.triangle", missing)
        } else if !s.hdr_folder.exists {
            placeholder("square.stack.3d.up", "Choose a folder to find your bracketed shots.")
        } else if busy && job.kind.str == "scan" {
            let p = job.progress
            VStack(spacing: 12) {
                ProgressView(value: p.exists ? p.done.double / max(p.total.double, 1) : nil).frame(width: 260).tint(brand)
                Text(p.stage.str == "Making previews" ? "Making previews · \(p.done.int) of \(p.total.int)"
                     : p.exists ? "Reading \(p.done.int.formatted()) of \(p.total.int.formatted()) photos" : "Looking for bracketed shots…")
                    .font(.callout).foregroundStyle(.secondary).monospacedDigit()
            }.frame(maxWidth: .infinity, maxHeight: .infinity)
        } else if let sets {
            if sets.isEmpty {
                placeholder("camera.aperture", "No bracketed shots here or in its subfolders.\nShoot with exposure bracketing (BRK C), in RAW.")
            } else {
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 10, pinnedViews: []) {
                        summary
                        ForEach(groups, id: \.0) { folder, items in
                            Text(folder.isEmpty ? "This folder" : folder.replacingOccurrences(of: "/", with: " › "))
                                .font(.system(size: 11.5, weight: .semibold)).foregroundStyle(.secondary).padding(.top, 6)
                            LazyVGrid(columns: [GridItem(.adaptive(minimum: 230), spacing: 12)], spacing: 12) {
                                ForEach(items) { card($0) }
                            }
                        }
                    }
                    .padding(18)
                }
            }
        } else {
            ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity)
        }
    }

    var groups: [(String, [BracketSet])] {
        var order: [String] = [], by: [String: [BracketSet]] = [:]
        for set in sets ?? [] {
            if by[set.folder] == nil { order.append(set.folder) }
            by[set.folder, default: []].append(set)
        }
        return order.map { ($0, by[$0]!) }
    }

    var summary: some View {
        let all = sets ?? [], done = all.filter(\.done).count
        return HStack {
            Text("\(plural(all.count, "set")) found\(done > 0 ? ", \(done) already merged" : "")")
                .font(.system(size: 12.5)).foregroundStyle(.secondary)
            Spacer()
            Button("Select All") { selected = Set(all.map(\.id)) }
            Button("None") { selected = [] }
            Button { scan() } label: { Image(systemName: "arrow.clockwise") }.help("Look again")
        }
        .buttonStyle(.borderless).controlSize(.small)
    }

    func card(_ set: BracketSet) -> some View {
        let on = selected.contains(set.id)
        return Button {
            if on { selected.remove(set.id) } else { selected.insert(set.id) }
        } label: {
            VStack(alignment: .leading, spacing: 0) {
                ZStack(alignment: .topTrailing) {
                    Group {
                        if let img = set.thumb {
                            Image(nsImage: img).resizable().aspectRatio(contentMode: .fill)
                        } else {
                            Rectangle().fill(.fill.tertiary).overlay(Image(systemName: "photo").foregroundStyle(.tertiary))
                        }
                    }
                    .frame(height: 132).frame(maxWidth: .infinity).clipped()
                    Image(systemName: on ? "checkmark.circle.fill" : "circle")
                        .font(.system(size: 20, weight: .medium))
                        .symbolRenderingMode(.palette)
                        .foregroundStyle(on ? Color.white : Color.white.opacity(0.9), on ? brand : Color.black.opacity(0.25))
                        .shadow(color: .black.opacity(0.35), radius: 3)
                        .padding(9)
                    if set.done {
                        Label("Merged", systemImage: "checkmark").font(.system(size: 10.5, weight: .semibold))
                            .padding(.horizontal, 7).padding(.vertical, 3)
                            .background(.ultraThinMaterial, in: Capsule())
                            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .bottomLeading).padding(9)
                    }
                }
                .frame(height: 132)
                VStack(alignment: .leading, spacing: 2) {
                    HStack {
                        Text("\(set.date) · \(set.time)").font(.system(size: 12.5, weight: .semibold))
                        Spacer()
                        if set.done {
                            Button { Task { await say(engine.act("/api/reveal", ["id": set.id])) } } label: {
                                Image(systemName: "magnifyingglass.circle")
                            }.buttonStyle(.borderless).help("Show in Finder")
                        }
                    }
                    Text("\(set.title) · \(set.evs)")
                        .font(.system(size: 11)).foregroundStyle(.secondary).lineLimit(1)
                }
                .padding(.horizontal, 11).padding(.vertical, 9)
            }
            .background(.fill.quinary)
            .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 14, style: .continuous)
                .strokeBorder(on ? brand : Color.primary.opacity(0.1), lineWidth: on ? 2 : 0.5))
            .contentShape(RoundedRectangle(cornerRadius: 14))
        }
        .buttonStyle(.plain)
    }

    func placeholder(_ symbol: String, _ text: String) -> some View {
        VStack(spacing: 12) {
            Image(systemName: symbol).font(.system(size: 34, weight: .light)).foregroundStyle(.tertiary)
            Text(text).font(.callout).foregroundStyle(.secondary).multilineTextAlignment(.center)
        }.frame(maxWidth: .infinity, maxHeight: .infinity).padding(30)
    }

    // MARK: merging

    var bottomBar: some View {
        HStack(spacing: 14) {
            if busy && job.kind.str == "merge" {
                let p = job.progress, f = p.done.double / max(p.total.double, 1)
                VStack(alignment: .leading, spacing: 4) {
                    Text("Merging \(p.name.str.replacingOccurrences(of: "_HDR.jpg", with: "")) · \(p.stage.str)")
                        .font(.system(size: 12, weight: .medium))
                    ProgressView(value: f).tint(brand)
                    Text("\(min(Int(p.done.double) + 1, p.total.int)) of \(plural(p.total.int, "set")) · about 30 seconds each")
                        .font(.system(size: 11)).foregroundStyle(.secondary)
                }
            } else {
                if let note {
                    Label(note.text, systemImage: note.bad ? "exclamationmark.circle.fill" : "checkmark.circle.fill")
                        .font(.system(size: 12)).foregroundStyle(note.bad ? Color.red : Color.green).lineLimit(2)
                } else {
                    Toggle("Also save a 16-bit TIFF for editing", isOn: $tiff).toggleStyle(.checkbox).font(.system(size: 12))
                }
                Spacer()
                Button {
                    Task { await say(engine.act("/api/hdr/merge", ["ids": Array(selected).sorted(), "tiff": tiff])) }
                } label: {
                    Text(selected.isEmpty ? "Choose Sets to Merge" : "Merge \(plural(selected.count, "Set"))").padding(.horizontal, 8)
                }
                .primaryAction()
                .disabled(selected.isEmpty || busy)
                .keyboardShortcut(.defaultAction)
            }
        }
        .padding(.horizontal, 18).padding(.vertical, 12)
        .background(.bar)
    }

    // MARK: talking to the engine

    func start() {
        if s.hdr_folder.exists && sets == nil {
            if job.state.str == "done" { load() } else if !busy { scan() }
        }
    }

    func setFolder(_ path: String) {
        Task { await say(engine.act("/api/hdr/folder", ["path": path])) }
    }

    func scan() {
        guard s.hdr_folder.exists, !busy else { return }
        Task { await say(engine.act("/api/hdr/scan")) }
    }

    func jobChanged() {
        guard job.state.str != "running", job.id.double != seenJob else { return }
        seenJob = job.id.double
        if job.state.str == "error" { note = (job.error.str, true); return }
        if job.kind.str == "merge", job.result.exists {
            let merged = job.result.merged.int, failed = job.result.failed.array.count
            note = failed > 0 ? ("\(plural(failed, "set")) couldn't be merged: \(job.result.failed[0].error.str)", true)
                : ("Saved \(plural(merged, "HDR photo")) in the day's HDR folder.", false)
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
        if let error { note = (error, true) }
    }
}
