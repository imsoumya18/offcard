"""ShotLoft in the macOS menu bar.

A status item (the aperture icon) opens a borderless panel on Liquid Glass (NSGlassEffectView on
macOS 26 and newer, the frosted NSVisualEffectView before that). The panel shows the app's own page
(ui/index.html, compact "pop" view) in a transparent WKWebView, so the glass shows through.
HDR Merge opens in a small window of its own, on the same glass.

In the background it watches for memory cards: when one with new files goes in, it posts a
notification and puts a dot on the icon; while copying, the icon shows a progress ring.
The app has no Dock icon (LSUIElement in the built app; the accessory activation policy here).
"""
import json
import math
import subprocess

import objc
from AppKit import (NSApplication, NSApplicationActivationPolicyAccessory, NSBackingStoreBuffered,
                    NSBezierPath, NSColor, NSEvent, NSEventMaskLeftMouseDown, NSEventMaskRightMouseDown,
                    NSImage, NSMakeRect, NSPanel, NSScreen, NSStatusBar, NSVariableStatusItemLength,
                    NSVisualEffectBlendingModeBehindWindow, NSVisualEffectMaterialPopover,
                    NSVisualEffectStateActive, NSVisualEffectView, NSWindow, NSWindowCollectionBehaviorCanJoinAllSpaces,
                    NSWindowCollectionBehaviorFullScreenAuxiliary, NSWindowStyleMaskBorderless,
                    NSWindowStyleMaskClosable, NSWindowStyleMaskFullSizeContentView,
                    NSWindowStyleMaskMiniaturizable, NSWindowStyleMaskNonactivatingPanel,
                    NSWindowStyleMaskResizable, NSWindowStyleMaskTitled, NSStatusWindowLevel,
                    NSViewHeightSizable, NSViewWidthSizable)
from Foundation import NSURL, NSURLRequest, NSObject, NSTimer, NSMakeSize, NSBundle
from PyObjCTools import AppHelper
import WebKit

GlassView = getattr(__import__("AppKit"), "NSGlassEffectView", None)  # macOS 26+

PANEL_W = 360
RADIUS = 22


# ---------------------------------------------------------------- icon

def icon(dot=False, progress=None):
    """The aperture as a template image (the menu bar tints it), with a dot for "new files on the
    card" or a ring for copy progress (0..1)."""
    size = NSMakeSize(20, 18)

    def draw(rect):
        NSColor.blackColor().set()
        cx, cy, r = 10.0, 9.0, 7.2
        ring = NSBezierPath.bezierPathWithOvalInRect_(NSMakeRect(cx - r, cy - r, 2 * r, 2 * r))
        if progress is None:
            ring.setLineWidth_(1.5)
            ring.stroke()
        else:  # a faint full ring, and the done part solid, clockwise from the top
            NSColor.colorWithWhite_alpha_(0, 0.3).set()
            ring.setLineWidth_(1.8)
            ring.stroke()
            NSColor.blackColor().set()
            arc = NSBezierPath.bezierPath()
            arc.appendBezierPathWithArcWithCenter_radius_startAngle_endAngle_clockwise_(
                (cx, cy), r, 90, 90 - 360 * max(0.02, min(progress, 1)), True)
            arc.setLineWidth_(1.8)
            arc.stroke()
        # six blades: chords that leave a hexagon in the middle
        blades = NSBezierPath.bezierPath()
        hr = 2.6
        for k in range(6):
            a = math.radians(90 + 60 * k)
            px, py = cx + hr * math.cos(a), cy + hr * math.sin(a)
            b = a + math.radians(60)
            blades.moveToPoint_((px, py))
            blades.lineToPoint_((cx + r * math.cos(b + 0.35), cy + r * math.sin(b + 0.35)))
        blades.setLineWidth_(1.1)
        blades.stroke()
        if dot:
            NSBezierPath.bezierPathWithOvalInRect_(NSMakeRect(15.2, 12.2, 4.8, 4.8)).fill()
        return True

    img = NSImage.imageWithSize_flipped_drawingHandler_(size, False, draw)
    img.setTemplate_(True)
    img.setAccessibilityDescription_("ShotLoft")
    return img


# ---------------------------------------------------------------- glass

def glass(frame, radius):
    """A Liquid Glass background (or the frosted material on older macOS) filling frame."""
    if GlassView is not None:
        g = GlassView.alloc().initWithFrame_(frame)
        g.setCornerRadius_(radius)
        return g, g.setContentView_
    v = NSVisualEffectView.alloc().initWithFrame_(frame)
    v.setMaterial_(NSVisualEffectMaterialPopover)
    v.setBlendingMode_(NSVisualEffectBlendingModeBehindWindow)
    v.setState_(NSVisualEffectStateActive)
    v.setWantsLayer_(True)
    v.layer().setCornerRadius_(radius)
    v.layer().setMasksToBounds_(True)

    def put(view):
        view.setFrame_(v.bounds())
        v.addSubview_(view)
    return v, put


def transparent_webview(frame, url, handler):
    cfg = WebKit.WKWebViewConfiguration.alloc().init()
    cfg.userContentController().addScriptMessageHandler_name_(handler, "shotloft")
    wv = WebKit.WKWebView.alloc().initWithFrame_configuration_(frame, cfg)
    wv.setValue_forKey_(False, "drawsBackground")        # let the glass show through
    wv.setUnderPageBackgroundColor_(NSColor.clearColor())
    wv.setAutoresizingMask_(NSViewWidthSizable | NSViewHeightSizable)
    wv.loadRequest_(NSURLRequest.requestWithURL_(NSURL.URLWithString_(url)))
    return wv


class KeyPanel(NSPanel):
    def canBecomeKeyWindow(self):
        return True


# ---------------------------------------------------------------- the app

class Controller(NSObject):
    def initWithURL_hooks_(self, url, hooks):
        self = objc.super(Controller, self).init()
        self.url, self.hooks = url, hooks
        self.hdr_window = None
        self.monitor = None
        self.icon_state = None
        return self

    # -- set-up
    def applicationDidFinishLaunching_(self, _):
        self.item = NSStatusBar.systemStatusBar().statusItemWithLength_(NSVariableStatusItemLength)
        self.item.button().setImage_(icon())
        self.item.button().setTarget_(self)
        self.item.button().setAction_("toggle:")

        frame = NSMakeRect(0, 0, PANEL_W, 300)
        self.panel = KeyPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            frame, NSWindowStyleMaskBorderless | NSWindowStyleMaskNonactivatingPanel, NSBackingStoreBuffered, False)
        self.panel.setOpaque_(False)
        self.panel.setBackgroundColor_(NSColor.clearColor())
        self.panel.setHasShadow_(True)
        self.panel.setLevel_(NSStatusWindowLevel)
        self.panel.setCollectionBehavior_(NSWindowCollectionBehaviorCanJoinAllSpaces
                                          | NSWindowCollectionBehaviorFullScreenAuxiliary)
        self.panel.setDelegate_(self)
        bg, put = glass(frame, RADIUS)
        self.web = transparent_webview(frame, self.url + "&view=pop", self)
        put(self.web)
        self.panel.setContentView_(bg)

        self.hooks["main"] = lambda fn: AppHelper.callAfter(fn)
        self.hooks["open_hdr"] = lambda: AppHelper.callAfter(self.openHDR)
        self.hooks["close_panel"] = lambda: AppHelper.callAfter(self.hidePanel)
        self.hooks["quit"] = lambda: AppHelper.callAfter(NSApplication.sharedApplication().terminate_, None)
        self.timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            1.0, self, "tick:", None, True)
        self.hooks["started"]()
        if self.hooks.get("open_on_start"):  # development: SHOTLOFT_OPEN_PANEL=1 opens the panel at launch
            AppHelper.callLater(1.5, self.showPanel)

    # -- the panel
    def toggle_(self, _):
        self.hidePanel() if self.panel.isVisible() else self.showPanel()

    def showPanel(self):
        self.place(self.panel.frame().size.height)
        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
        self.panel.makeKeyAndOrderFront_(None)
        self.web.evaluateJavaScript_completionHandler_("window.onPanelOpen && onPanelOpen()", None)
        if self.monitor is None:  # a click anywhere else closes it, like a menu
            self.monitor = NSEvent.addGlobalMonitorForEventsMatchingMask_handler_(
                NSEventMaskLeftMouseDown | NSEventMaskRightMouseDown, lambda e: self.hidePanel())

    def hidePanel(self):
        self.panel.orderOut_(None)
        if self.monitor is not None:
            NSEvent.removeMonitor_(self.monitor)
            self.monitor = None

    @objc.python_method
    def place(self, height):
        """Just under the menu bar icon, kept on screen."""
        button = self.item.button()
        bf = button.window().convertRectToScreen_(button.convertRect_toView_(button.bounds(), None))
        screen = (button.window().screen() or NSScreen.mainScreen()).visibleFrame()
        x = bf.origin.x + bf.size.width / 2 - PANEL_W / 2
        x = max(screen.origin.x + 8, min(x, screen.origin.x + screen.size.width - PANEL_W - 8))
        top = bf.origin.y - 6
        self.panel.setFrame_display_(NSMakeRect(x, top - height, PANEL_W, height), True)

    def windowDidResignKey_(self, note):
        if note.object() is self.panel:
            self.hidePanel()

    # -- messages from the page
    def userContentController_didReceiveScriptMessage_(self, _controller, message):
        try:
            msg = json.loads(message.body()) if isinstance(message.body(), str) else dict(message.body())
        except Exception:
            return
        if msg.get("type") == "size" and message.webView() is self.web:
            h = max(120, min(int(msg.get("height", 300)), 720))
            if abs(h - self.panel.frame().size.height) >= 1:
                self.place(h)

    # -- HDR Merge window
    def openHDR(self):
        self.hidePanel()
        if self.hdr_window is None:
            frame = NSMakeRect(0, 0, 600, 680)
            w = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
                frame, NSWindowStyleMaskTitled | NSWindowStyleMaskClosable | NSWindowStyleMaskMiniaturizable
                | NSWindowStyleMaskResizable | NSWindowStyleMaskFullSizeContentView, NSBackingStoreBuffered, False)
            w.setTitle_("HDR Merge")
            w.setTitlebarAppearsTransparent_(True)
            w.setOpaque_(False)
            w.setBackgroundColor_(NSColor.clearColor())
            w.setMinSize_(NSMakeSize(480, 420))
            w.setReleasedWhenClosed_(False)
            bg, put = glass(frame, 0)
            bg.setAutoresizingMask_(NSViewWidthSizable | NSViewHeightSizable)
            put(transparent_webview(frame, self.url + "&view=window#hdr", self))
            w.setContentView_(bg)
            w.center()
            self.hdr_window = w
        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
        self.hdr_window.makeKeyAndOrderFront_(None)

    # -- reopening the app (double-click in Applications) shows the panel
    def applicationShouldHandleReopen_hasVisibleWindows_(self, _app, _flag):
        self.showPanel()
        return False

    # -- the icon follows what's going on
    def tick_(self, _):
        state = self.hooks["icon_state"]()
        if state != self.icon_state:
            self.icon_state = state
            kind, value = state
            self.item.button().setImage_(icon(dot=kind == "new", progress=value if kind == "copy" else None))
            self.item.button().setToolTip_(self.hooks["tooltip"]())


# ---------------------------------------------------------------- notifications and login item

def bundled():
    bid = NSBundle.mainBundle().bundleIdentifier()
    return bool(bid) and bid.startswith("io.github.imsoumya18")


def notify(title, body):
    """A macOS notification. The built app posts its own; from source, it goes through osascript."""
    if bundled():
        try:
            import UserNotifications as UN
            center = UN.UNUserNotificationCenter.currentNotificationCenter()
            center.requestAuthorizationWithOptions_completionHandler_(
                UN.UNAuthorizationOptionAlert | UN.UNAuthorizationOptionSound, lambda ok, err: None)
            content = UN.UNMutableNotificationContent.alloc().init()
            content.setTitle_(title)
            content.setBody_(body)
            req = UN.UNNotificationRequest.requestWithIdentifier_content_trigger_("shotloft-card", content, None)
            center.addNotificationRequest_withCompletionHandler_(req, None)
            return
        except Exception:
            pass
    script = f'display notification {json.dumps(body)} with title {json.dumps(title)}'
    subprocess.Popen(["osascript", "-e", script], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def login_item(enable=None):
    """Whether ShotLoft opens at login (built app in a folder like Applications only). With
    enable, turn it on or off. Returns True/False, or None where it isn't available."""
    if not bundled():
        return None
    try:
        from ServiceManagement import SMAppService
        svc = SMAppService.mainAppService()
        if enable is True and svc.status() != 1:
            svc.registerAndReturnError_(None)
        elif enable is False and svc.status() == 1:
            svc.unregisterAndReturnError_(None)
        return svc.status() == 1   # SMAppServiceStatusEnabled
    except Exception:
        return None


def run(url, hooks):
    """Start the menu bar app; returns when ShotLoft quits."""
    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)  # no Dock icon
    ctl = Controller.alloc().initWithURL_hooks_(url, hooks)
    app.setDelegate_(ctl)
    AppHelper.runEventLoop(installInterrupt=True)
