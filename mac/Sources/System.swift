// macOS integration: notifications, opening at login, folder pickers, Finder, and the menu bar icon.

import AppKit
import ServiceManagement
import UserNotifications

enum System {
    // MARK: notifications

    static func askForNotifications() {
        UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound]) { _, _ in }
    }

    static func notify(_ title: String, _ body: String) {
        let content = UNMutableNotificationContent()
        content.title = title
        content.body = body
        content.sound = .default
        let req = UNNotificationRequest(identifier: "shotloft-card", content: content, trigger: nil)
        UNUserNotificationCenter.current().add(req)
    }

    // MARK: opening at login

    static var opensAtLogin: Bool { SMAppService.mainApp.status == .enabled }

    static func setOpensAtLogin(_ on: Bool) {
        do {
            if on { try SMAppService.mainApp.register() } else { try SMAppService.mainApp.unregister() }
        } catch {
            NSLog("ShotLoft: couldn't change open at login: \(error)")
        }
    }

    /// Turn it on once, the first time ShotLoft runs; after that it's the user's switch.
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

    /// The aperture (SF Symbol) as a template image, with a dot when a card has new files, or a
    /// progress ring (0...1) while copying.
    static func menuBarIcon(dot: Bool = false, progress: Double? = nil) -> NSImage {
        let size = NSSize(width: 22, height: 18)
        let img = NSImage(size: size, flipped: false) { _ in
            let config = NSImage.SymbolConfiguration(pointSize: 14, weight: .medium)
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
                if let s = NSImage(systemSymbolName: "arrow.down", accessibilityDescription: nil)?
                    .withSymbolConfiguration(NSImage.SymbolConfiguration(pointSize: 8, weight: .bold)) {
                    s.draw(in: NSRect(x: c.x - s.size.width / 2, y: c.y - s.size.height / 2,
                                      width: s.size.width, height: s.size.height))
                }
            } else if let s = NSImage(systemSymbolName: "camera.aperture", accessibilityDescription: "ShotLoft")?
                        .withSymbolConfiguration(config) {
                s.draw(in: NSRect(x: (size.width - s.size.width) / 2 - (dot ? 1.5 : 0),
                                  y: (size.height - s.size.height) / 2, width: s.size.width, height: s.size.height))
            }
            if dot {
                NSColor.black.setFill()
                NSBezierPath(ovalIn: NSRect(x: 16.5, y: 11.5, width: 5.5, height: 5.5)).fill()
            }
            return true
        }
        img.isTemplate = true
        return img
    }
}
