// macOS integration: opening at login, folder pickers, Finder, and the menu bar icon.

import AppKit
import ServiceManagement

enum System {
    // MARK: opening at login

    static var opensAtLogin: Bool { SMAppService.mainApp.status == .enabled }

    static func setOpensAtLogin(_ on: Bool) {
        do {
            if on { try SMAppService.mainApp.register() } else { try SMAppService.mainApp.unregister() }
        } catch {
            NSLog("offcard: couldn't change open at login: \(error)")
        }
    }

    /// Turn it on once, the first time offcard runs; after that it's the user's switch.
    static func setUpLoginItemOnce() {
        let key = "loginItemSetUp"
        guard !UserDefaults.standard.bool(forKey: key) else { return }
        UserDefaults.standard.set(true, forKey: key)
        setOpensAtLogin(true)
    }

    // MARK: folders

    @MainActor
    static func chooseFolder(_ message: String, startingAt path: String?) -> String? {
        NSApp.activate(ignoringOtherApps: true)
        let panel = NSOpenPanel()
        panel.canChooseDirectories = true
        panel.canChooseFiles = false
        panel.canCreateDirectories = true
        panel.allowsMultipleSelection = false
        panel.message = message
        panel.prompt = "Choose"
        if let path { panel.directoryURL = URL(fileURLWithPath: path) }
        return panel.runModal() == .OK ? panel.url?.path : nil
    }

    static func showInFinder(_ path: String) {
        NSWorkspace.shared.open(URL(fileURLWithPath: path))
    }

    // MARK: the menu bar icon

    /// offcard's three chevrons (the app icon's mark) as a template image, with a dot when a card
    /// has new files, or a progress ring (0...1) around one chevron while copying.
    static func menuBarIcon(dot: Bool = false, progress: Double? = nil) -> NSImage {
        let size = NSSize(width: 22, height: 18)
        let img = NSImage(size: size, flipped: false) { _ in
            func chevron(x: CGFloat, alpha: CGFloat, height h: CGFloat = 9, width w: CGFloat = 3.8, lineWidth: CGFloat = 1.9) {
                let p = NSBezierPath()
                p.move(to: NSPoint(x: x, y: 9 + h / 2))
                p.line(to: NSPoint(x: x + w, y: 9))
                p.line(to: NSPoint(x: x, y: 9 - h / 2))
                p.lineWidth = lineWidth
                p.lineCapStyle = .round
                p.lineJoinStyle = .round
                NSColor.black.withAlphaComponent(alpha).setStroke()
                p.stroke()
            }
            if let progress {
                let r: CGFloat = 7.6, c = NSPoint(x: 11, y: 9)
                let track = NSBezierPath(ovalIn: NSRect(x: c.x - r, y: c.y - r, width: 2 * r, height: 2 * r))
                NSColor.black.withAlphaComponent(0.28).setStroke()
                track.lineWidth = 2
                track.stroke()
                let arc = NSBezierPath()
                arc.appendArc(withCenter: c, radius: r, startAngle: 90,
                              endAngle: 90 - 360 * max(0.03, min(progress, 1)), clockwise: true)
                arc.lineWidth = 2
                arc.lineCapStyle = .round
                NSColor.black.setStroke()
                arc.stroke()
                chevron(x: c.x - 1.6, alpha: 1, height: 6, width: 3, lineWidth: 1.8)
            } else {
                let start: CGFloat = dot ? 3.5 : 5
                for (i, alpha) in [0.45, 0.72, 1.0].enumerated() {
                    chevron(x: start + CGFloat(i) * 4.6, alpha: alpha)
                }
            }
            if dot {
                NSColor.black.setFill()
                NSBezierPath(ovalIn: NSRect(x: 16.5, y: 11.5, width: 5.5, height: 5.5)).fill()
            }
            return true
        }
        img.isTemplate = true
        img.accessibilityDescription = "offcard"
        return img
    }
}
