// offcard for Windows: a tray app (Tauri) in front of the offcard engine.
//
//   offcard            the tray app, with the panel open
//   offcard --hidden   the tray app, panel closed (how Windows starts it at login)
//   offcard --check    start the engine, ask it for its state, exit 0 if it answers (tests)
//
// The panel itself is desktop/panel. This file is what a web page can't do: the tray icon, the
// frameless window above it, the engine as a helper, folder pickers, and starting with Windows.

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use serde_json::{json, Value};
use std::io::{Read, Write};
use std::net::TcpStream;
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Mutex;
use std::time::{Duration, Instant};
use tauri::image::Image;
use tauri::menu::{Menu, MenuItem};
use tauri::tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent};
use tauri::{AppHandle, LogicalSize, Manager, PhysicalPosition, RunEvent, State, WebviewUrl, WebviewWindow, WebviewWindowBuilder, WindowEvent};
use tauri_plugin_autostart::{MacosLauncher, ManagerExt};
use tauri_plugin_dialog::DialogExt;

const PANEL_WIDTH: f64 = 392.0; // the panel's 360, its border, and room for its shadow
const TOAST_HEIGHT: f64 = 104.0;
const STARTING: &str = "starting";

#[derive(Default)]
struct Shared {
    engine: Mutex<Option<(String, String)>>, // host, token
    failure: Mutex<Option<String>>,
    child: Mutex<Option<Child>>,
    hidden_at: Mutex<Option<Instant>>, // when the panel last closed by losing focus
    tray_at: Mutex<Option<(f64, f64)>>, // the tray icon's centre, in screen pixels
    in_dialog: AtomicBool,             // a folder picker has focus: the panel stays
}

// ---- the engine

/// Starts the engine, naming a file for it to write its address and token in.
fn spawn_engine(url_file: &PathBuf, agent: bool) -> std::io::Result<Child> {
    let mut args: Vec<String> = vec!["--serve".into()];
    if agent {
        args.push("--agent".into());
    }
    let mut cmd = match std::env::var("OFFCARD_ENGINE").ok().filter(|v| !v.is_empty()) {
        Some(dev) => {
            // development: "python C:\path\to\offcard.py"
            let mut parts = dev.split(' ').map(String::from);
            let mut c = Command::new(parts.next().unwrap());
            c.args(parts);
            c
        }
        None => {
            let exe = std::env::current_exe()?;
            let dir = exe.parent().map(PathBuf::from).unwrap_or_default();
            Command::new(dir.join("engine").join(engine_name()))
        }
    };
    cmd.args(args)
        .env("OFFCARD_URL_FILE", url_file)
        .env("OFFCARD_PARENT_PID", std::process::id().to_string())
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null());
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        cmd.creation_flags(0x0800_0000); // CREATE_NO_WINDOW
    }
    cmd.spawn()
}

fn engine_name() -> &'static str {
    if cfg!(windows) { "OffcardEngine.exe" } else { "OffcardEngine" }
}

/// Waits for the engine's address, for up to a minute. None if it stopped or never wrote it.
fn read_address(file: &PathBuf, child: &mut Child) -> Result<(String, String), String> {
    for _ in 0..600 {
        if let Ok(text) = std::fs::read_to_string(file) {
            if let Ok(info) = serde_json::from_str::<Value>(&text) {
                let host = info["url"].as_str().unwrap_or("").split('/').nth(2).unwrap_or("").to_string();
                let token = info["token"].as_str().unwrap_or("").to_string();
                if !host.is_empty() && !token.is_empty() {
                    let _ = std::fs::remove_file(file);
                    return Ok((host, token));
                }
            }
        }
        if let Ok(Some(code)) = child.try_wait() {
            return Err(format!("offcard's engine stopped while starting ({code})."));
        }
        std::thread::sleep(Duration::from_millis(100));
    }
    Err("offcard's engine didn't start in time.".into())
}

/// One request to the engine, which closes the connection after each answer.
fn request(host: &str, token: &str, path: &str, body: Option<&Value>) -> Result<(u16, Value), String> {
    let addr = host.parse().map_err(|_| "Bad engine address.".to_string())?;
    let mut sock = TcpStream::connect_timeout(&addr, Duration::from_secs(5)).map_err(|e| e.to_string())?;
    sock.set_read_timeout(Some(Duration::from_secs(120))).ok();
    let payload = body.map(|b| b.to_string()).unwrap_or_default();
    let head = format!(
        "{} {path} HTTP/1.1\r\nHost: {host}\r\nX-Token: {token}\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n",
        if body.is_some() { "POST" } else { "GET" },
        payload.len()
    );
    sock.write_all(head.as_bytes()).and_then(|_| sock.write_all(payload.as_bytes())).map_err(|e| e.to_string())?;
    let mut raw = Vec::new();
    sock.read_to_end(&mut raw).map_err(|e| e.to_string())?;
    let split = raw.windows(4).position(|w| w == b"\r\n\r\n").ok_or("The engine gave no answer.")?;
    let status = String::from_utf8_lossy(&raw[..split]).split(' ').nth(1).and_then(|c| c.parse().ok()).unwrap_or(0);
    Ok((status, serde_json::from_slice(&raw[split + 4..]).unwrap_or(Value::Null)))
}

fn ask(shared: &Shared, path: &str, body: Option<&Value>) -> Result<Value, String> {
    let engine = shared.engine.lock().unwrap().clone();
    let Some((host, token)) = engine else {
        return Err(shared.failure.lock().unwrap().clone().unwrap_or_else(|| STARTING.into()));
    };
    let (status, json) = request(&host, &token, path, body)?;
    if status == 200 {
        Ok(json)
    } else {
        Err(json["error"].as_str().unwrap_or("Something went wrong.").to_string())
    }
}

fn start_engine(app: AppHandle) {
    std::thread::spawn(move || {
        let shared = app.state::<Shared>();
        let file = std::env::temp_dir().join(format!("offcard-{}.json", std::process::id()));
        let _ = std::fs::remove_file(&file);
        let mut child = match spawn_engine(&file, true) {
            Ok(c) => c,
            Err(e) => {
                *shared.failure.lock().unwrap() = Some(format!("offcard's engine couldn't start: {e}"));
                return;
            }
        };
        let address = read_address(&file, &mut child);
        *shared.child.lock().unwrap() = Some(child);
        match address {
            Ok(a) => *shared.engine.lock().unwrap() = Some(a),
            Err(e) => *shared.failure.lock().unwrap() = Some(e),
        }
    });
}

fn stop_engine(shared: &Shared) {
    if let Some(mut child) = shared.child.lock().unwrap().take() {
        let _ = child.kill();
    }
}

/// `--check`: the bundled engine starts and answers. No window, for CI and the installer.
fn check() -> i32 {
    let file = std::env::temp_dir().join(format!("offcard-check-{}.json", std::process::id()));
    let Ok(mut child) = spawn_engine(&file, false) else { return 2 };
    let result = read_address(&file, &mut child).and_then(|(host, token)| request(&host, &token, "/api/state", None));
    let _ = child.kill();
    match result {
        Ok((200, state)) if state["version"].as_str() == Some(env!("CARGO_PKG_VERSION")) => 0,
        Ok(_) => 3,
        Err(_) => 4,
    }
}

// ---- the tray icon

/// How much of a pixel a stroke from a to b covers.
fn stroke(px: (f64, f64), a: (f64, f64), b: (f64, f64), width: f64) -> f64 {
    let (dx, dy) = (b.0 - a.0, b.1 - a.1);
    let t = (((px.0 - a.0) * dx + (px.1 - a.1) * dy) / (dx * dx + dy * dy)).clamp(0.0, 1.0);
    let d = ((px.0 - a.0 - t * dx).powi(2) + (px.1 - a.1 - t * dy).powi(2)).sqrt();
    (width / 2.0 + 0.5 - d).clamp(0.0, 1.0)
}

/// offcard's three chevrons, with a dot when a card has new files, or a progress ring (0...1)
/// around one chevron while copying. Drawn on a 22 × 18 grid, like the Mac's.
fn tray_image(dot: bool, progress: Option<f64>, light_taskbar: bool) -> Image<'static> {
    const SIZE: u32 = 32;
    let scale = SIZE as f64 / 22.0;
    let top = (SIZE as f64 - 18.0 * scale) / 2.0;
    let ink: u8 = if light_taskbar { 26 } else { 255 };
    let mut rgba = Vec::with_capacity((SIZE * SIZE * 4) as usize);
    for y in 0..SIZE {
        for x in 0..SIZE {
            let (gx, gy) = ((x as f64 + 0.5) / scale, (y as f64 + 0.5 - top) / scale);
            let chevron = |cx: f64, h: f64, w: f64, lw: f64| {
                let p = (gx * scale, gy * scale);
                let at = |a: f64, b: f64| (a * scale, b * scale);
                stroke(p, at(cx, 9.0 - h / 2.0), at(cx + w, 9.0), lw * scale)
                    .max(stroke(p, at(cx + w, 9.0), at(cx, 9.0 + h / 2.0), lw * scale))
            };
            let mut alpha: f64 = 0.0;
            if let Some(p) = progress {
                let (dx, dy) = (gx - 11.0, gy - 9.0);
                let band = ((1.0 + 0.5 / scale - ((dx * dx + dy * dy).sqrt() - 7.6).abs()) * scale).clamp(0.0, 1.0);
                let turned = dx.atan2(-dy).rem_euclid(std::f64::consts::TAU) / std::f64::consts::TAU;
                alpha = alpha.max(band * if turned <= p.clamp(0.03, 1.0) { 1.0 } else { 0.28 });
                alpha = alpha.max(chevron(9.4, 6.0, 3.0, 1.8));
            } else {
                let start = if dot { 3.5 } else { 5.0 };
                for (i, a) in [0.45, 0.72, 1.0].iter().enumerate() {
                    alpha = alpha.max(a * chevron(start + i as f64 * 4.6, 9.0, 3.8, 1.9));
                }
            }
            if dot {
                let d = ((gx - 19.25).powi(2) + (gy - 3.75).powi(2)).sqrt();
                alpha = alpha.max(((2.75 - d) * scale + 0.5).clamp(0.0, 1.0));
            }
            rgba.extend_from_slice(&[ink, ink, ink, (alpha * 255.0).round() as u8]);
        }
    }
    Image::new_owned(rgba, SIZE, SIZE)
}

fn taskbar_is_light() -> bool {
    #[cfg(windows)]
    {
        use winreg::enums::HKEY_CURRENT_USER;
        let key = winreg::RegKey::predef(HKEY_CURRENT_USER)
            .open_subkey(r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize");
        if let Ok(key) = key {
            return key.get_value::<u32, _>("SystemUsesLightTheme").unwrap_or(0) == 1;
        }
    }
    false
}

/// Looks at the engine all the time, even with the panel closed: keeps the icon current, and
/// says so when a card with new files goes in.
fn watch(app: AppHandle) {
    std::thread::spawn(move || {
        let shared = app.state::<Shared>();
        let mut shown = String::new();
        let mut told = String::new();
        loop {
            let state = ask(&shared, "/api/state", None).unwrap_or(Value::Null);
            let job = &state["job"];
            let copying = job["kind"] == "import" && job["state"] == "running";
            let cards = state["cards"].to_string();
            let empty = state["cards"].as_array().map_or(true, |c| c.is_empty());
            let planned = job["kind"] == "plan" && job["state"] == "done" && !empty;
            let new_files = job["result"]["new_files"].as_u64().unwrap_or(0);
            let fresh = planned && new_files > 0;

            let progress = copying.then(|| {
                job["progress"]["done"].as_f64().unwrap_or(0.0) / job["progress"]["total"].as_f64().unwrap_or(1.0).max(1.0)
            });
            let light = taskbar_is_light();
            let look = format!("{fresh} {light} {:?}", progress.map(|p| (p * 20.0) as i32));
            if look != shown {
                shown = look;
                if let Some(tray) = app.tray_by_id("main") {
                    let _ = tray.set_icon(Some(tray_image(fresh, progress, light)));
                }
            }

            if empty {
                told.clear();
            } else if fresh && told != cards {
                told = cards;
                let open = app.get_webview_window("main").map_or(false, |w| w.is_visible().unwrap_or(false));
                if !open {
                    let name = state["cards"][0]["name"].as_str().unwrap_or("A card").to_string();
                    let line = format!("{} new {}, {}", new_files, if new_files == 1 { "file" } else { "files" },
                                       human(job["result"]["needed_bytes"].as_f64().unwrap_or(0.0)));
                    show_toast(&app, &name, &line);
                }
            }
            std::thread::sleep(Duration::from_millis(if copying { 500 } else { 1500 }));
        }
    });
}

fn human(n: f64) -> String {
    const G: f64 = 1073741824.0;
    const M: f64 = 1048576.0;
    if n >= G { format!("{:.2} GB", n / G) } else if n >= M { format!("{:.1} MB", n / M) } else { format!("{:.0} KB", n / 1024.0) }
}

// ---- the panel and the notification

/// The screen area a window of this size goes in, next to the tray, as a top-left corner.
fn corner(app: &AppHandle, window: &WebviewWindow, width: f64, height: f64) -> Option<PhysicalPosition<i32>> {
    let at = *app.state::<Shared>().tray_at.lock().unwrap();
    let monitor = at
        .and_then(|(x, y)| app.monitor_from_point(x, y).ok().flatten())
        .or_else(|| window.primary_monitor().ok().flatten())?;
    let scale = monitor.scale_factor();
    let area = monitor.work_area();
    let (left, top) = (area.position.x as f64, area.position.y as f64);
    let (right, bottom) = (left + area.size.width as f64, top + area.size.height as f64);
    let (w, h) = (width * scale, height * scale);
    let (tx, ty) = at.unwrap_or((right, bottom));
    // Against the tray: its side of the screen, and as near to it as the screen allows. On a
    // taskbar at the left or right edge, that's beside the taskbar, which the work area leaves out.
    let x = if tx < left + (right - left) / 2.0 { left } else { right - w };
    let y = if ty < top + (bottom - top) / 2.0 { top } else { bottom - h };
    Some(PhysicalPosition::new(x as i32, y as i32))
}

fn place(app: &AppHandle, window: &WebviewWindow) {
    let size = window.inner_size().ok();
    let scale = window.scale_factor().unwrap_or(1.0);
    let height = size.map_or(326.0, |s| s.height as f64 / scale);
    if let Some(p) = corner(app, window, PANEL_WIDTH, height) {
        let _ = window.set_position(p);
    }
}

fn show_panel(app: &AppHandle) {
    if let Some(toast) = app.get_webview_window("toast") {
        let _ = toast.close();
    }
    if let Some(w) = app.get_webview_window("main") {
        place(app, &w);
        let _ = w.show();
        let _ = w.set_focus();
    }
}

fn toggle_panel(app: &AppHandle) {
    let Some(w) = app.get_webview_window("main") else { return };
    if w.is_visible().unwrap_or(false) {
        let _ = w.hide();
        return;
    }
    // Clicking the icon with the panel open first takes focus from the panel, which closes it:
    // that click should leave it closed, not open it again.
    let just_closed = app.state::<Shared>().hidden_at.lock().unwrap().map_or(false, |t| t.elapsed() < Duration::from_millis(400));
    if !just_closed {
        show_panel(app);
    }
}

fn encoded(text: &str) -> String {
    text.bytes().map(|b| match b {
        b'A'..=b'Z' | b'a'..=b'z' | b'0'..=b'9' | b'-' | b'_' | b'.' => (b as char).to_string(),
        _ => format!("%{b:02X}"),
    }).collect()
}

/// A small window above the tray: this icon may be tucked behind the ^, so a card going in needs
/// saying. It doesn't take focus, and leaves by itself.
fn show_toast(app: &AppHandle, card: &str, line: &str) {
    let (app, card, line) = (app.clone(), card.to_string(), line.to_string());
    let handle = app.clone();
    let _ = handle.run_on_main_thread(move || {
        if let Some(old) = app.get_webview_window("toast") {
            let _ = old.close();
        }
        let url = format!("index.html?card={}&line={}", encoded(&card), encoded(&line));
        let built = WebviewWindowBuilder::new(&app, "toast", WebviewUrl::App(url.into()))
            .title("offcard")
            .inner_size(PANEL_WIDTH, TOAST_HEIGHT)
            .decorations(false)
            .transparent(true)
            .shadow(false)
            .resizable(false)
            .skip_taskbar(true)
            .always_on_top(true)
            .focused(false)
            .visible(false)
            .build();
        let Ok(toast) = built else { return };
        if let Some(p) = corner(&app, &toast, PANEL_WIDTH, TOAST_HEIGHT) {
            let _ = toast.set_position(p);
        }
        let _ = toast.show();
        std::thread::spawn(move || {
            std::thread::sleep(Duration::from_secs(8));
            let _ = toast.close();
        });
    });
}

// ---- what the page asks for

#[tauri::command(async)]
fn api(shared: State<Shared>, path: String, body: Option<Value>) -> Result<Value, String> {
    ask(&shared, &path, body.as_ref())
}

/// The page's height changed (an update row came or went): keep the panel against the taskbar.
#[tauri::command]
fn fit(app: AppHandle, height: f64) {
    if let Some(w) = app.get_webview_window("main") {
        let _ = w.set_size(LogicalSize::new(PANEL_WIDTH, height));
        place(&app, &w);
    }
}

#[tauri::command]
fn open_panel(app: AppHandle) {
    show_panel(&app);
}

#[tauri::command]
fn hide_panel(app: AppHandle) {
    if let Some(w) = app.get_webview_window("main") {
        let _ = w.hide();
    }
}

#[tauri::command]
fn quit(app: AppHandle, shared: State<Shared>) {
    stop_engine(&shared);
    app.exit(0);
}

#[tauri::command(async)]
fn pick_folder(app: AppHandle, shared: State<Shared>, title: String, start: Option<String>) -> Option<String> {
    let window = app.get_webview_window("main")?;
    shared.in_dialog.store(true, Ordering::SeqCst);
    let mut dialog = app.dialog().file().set_title(title).set_parent(&window);
    if let Some(start) = start.filter(|s| std::path::Path::new(s).is_dir()) {
        dialog = dialog.set_directory(start);
    }
    let picked = dialog.blocking_pick_folder();
    shared.in_dialog.store(false, Ordering::SeqCst);
    let _ = window.set_focus();
    picked.map(|p| p.to_string())
}

#[tauri::command]
fn show_folder(path: String) {
    let _ = Command::new(if cfg!(windows) { "explorer" } else { "open" }).arg(path).spawn();
}

#[tauri::command]
fn login_get(app: AppHandle) -> bool {
    app.autolaunch().is_enabled().unwrap_or(false)
}

#[tauri::command]
fn login_set(app: AppHandle, on: bool) -> bool {
    let auto = app.autolaunch();
    let _ = if on { auto.enable() } else { auto.disable() };
    auto.is_enabled().unwrap_or(false)
}

/// Turn starting with Windows on once, the first time offcard runs; after that it's the user's switch.
fn set_up_login_once(app: &AppHandle) {
    let Ok(dir) = app.path().app_config_dir() else { return };
    let mark = dir.join("login-set-up");
    if std::env::var_os("OFFCARD_DEV").is_some() || mark.exists() {
        return;
    }
    let _ = app.autolaunch().enable();
    let _ = std::fs::create_dir_all(&dir).and_then(|_| std::fs::write(mark, json!(true).to_string()));
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    if args.iter().any(|a| a == "--check") {
        std::process::exit(check());
    }
    let hidden = args.iter().any(|a| a == "--hidden");

    let app = tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app, _, _| show_panel(app)))
        .plugin(tauri_plugin_autostart::init(MacosLauncher::LaunchAgent, Some(vec!["--hidden"])))
        .plugin(tauri_plugin_dialog::init())
        .manage(Shared::default())
        .invoke_handler(tauri::generate_handler![api, fit, open_panel, hide_panel, quit, pick_folder, show_folder, login_get, login_set])
        .setup(move |app| {
            let handle = app.handle().clone();
            set_up_login_once(&handle);

            let open = MenuItem::with_id(app, "open", "Open offcard", true, None::<&str>)?;
            let leave = MenuItem::with_id(app, "quit", "Quit", true, None::<&str>)?;
            let menu = Menu::with_items(app, &[&open, &leave])?;
            TrayIconBuilder::with_id("main")
                .icon(tray_image(false, None, taskbar_is_light()))
                .tooltip("offcard")
                .menu(&menu)
                .show_menu_on_left_click(false)
                .on_menu_event(|app, event| match event.id.as_ref() {
                    "open" => show_panel(app),
                    "quit" => {
                        stop_engine(&app.state::<Shared>());
                        app.exit(0);
                    }
                    _ => {}
                })
                .on_tray_icon_event(|tray, event| {
                    if let TrayIconEvent::Click { button: MouseButton::Left, button_state: MouseButtonState::Up, rect, .. } = event {
                        let app = tray.app_handle();
                        let (p, s) = (rect.position.to_physical::<f64>(1.0), rect.size.to_physical::<f64>(1.0));
                        *app.state::<Shared>().tray_at.lock().unwrap() = Some((p.x + s.width / 2.0, p.y + s.height / 2.0));
                        toggle_panel(app);
                    }
                })
                .build(app)?;

            start_engine(handle.clone());
            watch(handle.clone());
            if !hidden {
                // Windows tucks new tray icons behind the ^, so opening offcard opens the panel.
                show_panel(&handle);
            }
            Ok(())
        })
        .on_window_event(|window, event| {
            if window.label() != "main" {
                return;
            }
            match event {
                WindowEvent::Focused(false) => {
                    // A moment later, and only if focus really left: clicks inside the page can
                    // pass focus around within the window.
                    let window = window.clone();
                    std::thread::spawn(move || {
                        std::thread::sleep(Duration::from_millis(80));
                        let shared = window.state::<Shared>();
                        if !shared.in_dialog.load(Ordering::SeqCst) && !window.is_focused().unwrap_or(false) {
                            *shared.hidden_at.lock().unwrap() = Some(Instant::now());
                            let _ = window.hide();
                        }
                    });
                }
                WindowEvent::CloseRequested { api, .. } => {
                    api.prevent_close();
                    let _ = window.hide();
                }
                _ => {}
            }
        })
        .build(tauri::generate_context!())
        .expect("offcard couldn't start");

    app.run(|app, event| {
        if let RunEvent::Exit = event {
            stop_engine(&app.state::<Shared>());
        }
    });
}
