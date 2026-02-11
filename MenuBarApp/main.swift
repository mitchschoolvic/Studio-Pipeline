#!/usr/bin/env swift

import Cocoa
import Foundation

class AppDelegate: NSObject, NSApplicationDelegate {
    var statusItem: NSStatusItem!
    var backendProcess: Process?
    var backendPID: Int32?

    // Server configuration - must match backend/constants.py ServerConfig
    let serverPort = 8888
    var backendURL: String { return "http://127.0.0.1:\(serverPort)" }
    var healthURL: String { return "http://127.0.0.1:\(serverPort)/api/health" }

    func applicationDidFinishLaunching(_ notification: Notification) {
        // Strong single-instance guard using atomic lock file (avoids race on rapid double-launch)
        let logDir = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Library/Logs/StudioPipeline")
        try? FileManager.default.createDirectory(at: logDir, withIntermediateDirectories: true)
        let lockFile = logDir.appendingPathComponent("instance.lock")
        let pid = getpid()
        // Attempt atomic creation
        let fd = open(lockFile.path, O_CREAT | O_EXCL | O_WRONLY, 0o644)
        if fd == -1 {
            // Lock exists - check if owning PID is alive
            if let existingPidStr = try? String(contentsOf: lockFile, encoding: .utf8),
               let existingPid = Int32(existingPidStr.trimmingCharacters(in: .whitespacesAndNewlines)),
               kill(existingPid, 0) == 0 {
                let alert = NSAlert()
                alert.messageText = "Studio Pipeline Already Running"
                alert.informativeText = "An instance (PID: \(existingPid)) is already active. This launch will exit."
                alert.alertStyle = .informational
                alert.addButton(withTitle: "OK")
                alert.runModal()
                NSApp.terminate(nil)
                return
            } else {
                // Stale lock - remove and recreate
                try? FileManager.default.removeItem(at: lockFile)
                let fdRetry = open(lockFile.path, O_CREAT | O_EXCL | O_WRONLY, 0o644)
                if fdRetry != -1 {
                    let pidString = "\(pid)".data(using: .utf8)!
                    pidString.withUnsafeBytes { write(fdRetry, $0.baseAddress, $0.count) }
                    close(fdRetry)
                }
            }
        } else {
            let pidString = "\(pid)".data(using: .utf8)!
            pidString.withUnsafeBytes { write(fd, $0.baseAddress, $0.count) }
            close(fd)
        }

        // Clean up any orphaned backend processes from previous runs
        cleanupOrphanedProcesses()
        
        // Create menu bar item
        statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)

        if let button = statusItem.button {
            button.title = "📹" // Video camera emoji as icon
            button.toolTip = "Studio Pipeline"
        }

        // Create menu
        let menu = NSMenu()

        menu.addItem(NSMenuItem(title: "Open Dashboard", action: #selector(openDashboard), keyEquivalent: "o"))
        menu.addItem(NSMenuItem(title: "Open Database Location", action: #selector(openDatabaseLocation), keyEquivalent: "d"))
        menu.addItem(NSMenuItem(title: "Open Log Location", action: #selector(openLogLocation), keyEquivalent: "l"))
        menu.addItem(NSMenuItem.separator())
        menu.addItem(NSMenuItem(title: "Backend Status: Starting...", action: nil, keyEquivalent: ""))
        menu.addItem(NSMenuItem.separator())
        menu.addItem(NSMenuItem(title: "Quit Studio Pipeline", action: #selector(quitApp), keyEquivalent: "q"))

        statusItem.menu = menu

        // Start backend
        startBackend()
    }

    func applicationWillTerminate(_ notification: Notification) {
        stopBackend()
        // Remove lock file on clean exit
        let lockFile = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Library/Logs/StudioPipeline/instance.lock")
        try? FileManager.default.removeItem(at: lockFile)
    }

    @objc func openDashboard() {
        if let url = URL(string: backendURL) {
            NSWorkspace.shared.open(url)
        }
    }

    @objc func openDatabaseLocation() {
        // Database is stored in ~/Library/Application Support/StudioPipeline/
        let dbDirectory = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Library/Application Support/StudioPipeline")

        // Create directory if it doesn't exist
        try? FileManager.default.createDirectory(at: dbDirectory, withIntermediateDirectories: true)

        // Open the directory in Finder
        NSWorkspace.shared.selectFile(nil, inFileViewerRootedAtPath: dbDirectory.path)
    }

    @objc func openLogLocation() {
        // Logs are stored in ~/Library/Application Support/StudioPipeline/logs/
        let logDirectory = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Library/Application Support/StudioPipeline/logs")

        // Create directory if it doesn't exist
        try? FileManager.default.createDirectory(at: logDirectory, withIntermediateDirectories: true)

        // Open the directory in Finder
        NSWorkspace.shared.selectFile(nil, inFileViewerRootedAtPath: logDirectory.path)
    }

    @objc func quitApp() {
        NSApplication.shared.terminate(self)
    }

    func cleanupOrphanedProcesses() {
        // Kill any process using our server port
        let task = Process()
        // Use /usr/bin/env to locate lsof on macOS (commonly at /usr/sbin/lsof)
        task.executableURL = URL(fileURLWithPath: "/usr/bin/env")
        task.arguments = ["lsof", "-ti", ":\(serverPort)"]
        
        let pipe = Pipe()
        task.standardOutput = pipe
        
        do {
            try task.run()
            task.waitUntilExit()
            
            let data = pipe.fileHandleForReading.readDataToEndOfFile()
            if let output = String(data: data, encoding: .utf8) {
                let pids = output.components(separatedBy: .newlines).filter { !$0.isEmpty }
                for pidString in pids {
                    if let pid = Int32(pidString.trimmingCharacters(in: .whitespaces)) {
                        print("Cleaning up orphaned process on port \(serverPort): PID \(pid)")
                        kill(pid, SIGKILL)
                    }
                }
            }
        } catch {
            print("Could not cleanup orphaned processes: \(error)")
        }
        
        // Also check PID file
        let logDir = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Library/Logs/StudioPipeline")
        let pidFile = logDir.appendingPathComponent("backend.pid")
        
        if let pidString = try? String(contentsOf: pidFile, encoding: .utf8),
           let pid = Int32(pidString.trimmingCharacters(in: .whitespaces)) {
            print("Found PID file with PID: \(pid)")
            // Check if process is still running
            if kill(pid, 0) == 0 {
                print("Killing stale backend process: \(pid)")
                kill(pid, SIGKILL)
            }
            try? FileManager.default.removeItem(at: pidFile)
        }
    }

    func startBackend() {
        // Get the path to the backend executable
        let bundle = Bundle.main
        let resourcePath = bundle.resourcePath ?? ""
        let backendPath = "\(resourcePath)/../MacOS/backend/backend"

        guard FileManager.default.fileExists(atPath: backendPath) else {
            updateStatusMessage("Backend Error: Not Found")
            showAlert(title: "Backend Error", message: "Backend executable not found at: \(backendPath)")
            return
        }

        // Setup log directory
        let logDir = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Library/Logs/StudioPipeline")
        try? FileManager.default.createDirectory(at: logDir, withIntermediateDirectories: true)

        let logFile = logDir.appendingPathComponent("backend.log")

        // Create process
        backendProcess = Process()
        backendProcess?.executableURL = URL(fileURLWithPath: backendPath)
        backendProcess?.currentDirectoryURL = URL(fileURLWithPath: resourcePath + "/../MacOS/backend")

        // Set environment variables
        var environment = ProcessInfo.processInfo.environment
        environment["PYTHONUNBUFFERED"] = "1"
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        
        // Detect AI build and set BUILD_WITH_AI accordingly
        let bundleId = bundle.bundleIdentifier ?? ""
        let aiModelsPath = resourcePath + "/../MacOS/backend/_internal/models/llm"
        let isAIBuild = bundleId.contains(".ai") || FileManager.default.fileExists(atPath: aiModelsPath)
        environment["BUILD_WITH_AI"] = isAIBuild ? "true" : "false"
        
        // Add bundled tools to PATH (for LAME and other tools used by Swift tools)
        // The bundled swift_tools directory contains both our custom tools and dependencies like LAME
        let bundledToolsPath = resourcePath + "/../MacOS/backend/_internal/swift_tools"
        
        // Also include Homebrew paths for development/local usage
        let additionalPaths = "\(bundledToolsPath):/opt/homebrew/bin:/opt/homebrew/sbin:/usr/local/bin"
        
        if let currentPath = environment["PATH"] {
            environment["PATH"] = "\(additionalPaths):\(currentPath)"
        } else {
            environment["PATH"] = "\(additionalPaths):/usr/bin:/bin:/usr/sbin:/sbin"
        }
        
        backendProcess?.environment = environment

        // Redirect output to log file
        if let logHandle = try? FileHandle(forWritingTo: logFile) {
            backendProcess?.standardOutput = logHandle
            backendProcess?.standardError = logHandle
        }

        // Start backend
        do {
            try backendProcess?.run()
            backendPID = backendProcess?.processIdentifier

            // Save PID to file
            let pidFile = logDir.appendingPathComponent("backend.pid")
            try? "\(backendPID ?? 0)".write(to: pidFile, atomically: true, encoding: .utf8)

            print("Backend started with PID: \(backendPID ?? 0)")
            updateStatusMessage("Backend Status: Starting...")

            // Wait for backend to be ready
            checkBackendHealth()
        } catch {
            updateStatusMessage("Backend Error: Failed to Start")
            showAlert(title: "Backend Error", message: "Failed to start backend: \(error.localizedDescription)")
        }
    }

    func checkBackendHealth() {
        var attempts = 0
        let maxAttempts = 30

        Timer.scheduledTimer(withTimeInterval: 1.0, repeats: true) { timer in
            attempts += 1

            if self.isBackendHealthy() {
                self.updateStatusMessage("Backend Status: Running ✓")
                timer.invalidate()

                // Open dashboard on first launch
                self.openDashboard()
            } else if attempts >= maxAttempts {
                self.updateStatusMessage("Backend Status: Failed to Start")
                timer.invalidate()
                self.showAlert(title: "Backend Error", message: "Backend failed to start within \(maxAttempts) seconds")
            }
        }
    }

    func isBackendHealthy() -> Bool {
        guard let url = URL(string: healthURL) else { return false }

        let semaphore = DispatchSemaphore(value: 0)
        var isHealthy = false

        let task = URLSession.shared.dataTask(with: url) { data, response, error in
            if let httpResponse = response as? HTTPURLResponse, httpResponse.statusCode == 200 {
                isHealthy = true
            }
            semaphore.signal()
        }

        task.resume()
        _ = semaphore.wait(timeout: .now() + 2.0)

        return isHealthy
    }

    func stopBackend() {
        guard let pid = backendPID else { return }

        print("Stopping backend (PID: \(pid))...")

        // Send SIGTERM for graceful shutdown
        kill(pid, SIGTERM)

        // Wait a bit for graceful shutdown
        sleep(2)

        // Force kill if still running
        if kill(pid, 0) == 0 {
            print("Force stopping backend...")
            kill(pid, SIGKILL)
        }

        // Clean up PID file
        let logDir = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Library/Logs/StudioPipeline")
        let pidFile = logDir.appendingPathComponent("backend.pid")
        try? FileManager.default.removeItem(at: pidFile)

        print("Backend stopped")
    }

    func updateStatusMessage(_ message: String) {
        if let menu = statusItem.menu {
            // Update the status menu item (index 3, since we added "Open Database Location")
            if menu.items.count > 3 {
                menu.items[3].title = message
            }
        }
    }

    func showAlert(title: String, message: String) {
        let alert = NSAlert()
        alert.messageText = title
        alert.informativeText = message
        alert.alertStyle = .warning
        alert.addButton(withTitle: "OK")
        alert.runModal()
    }
}

// Main execution
let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate

// Set activation policy to regular (shows in dock AND menu bar)
app.setActivationPolicy(.regular)

app.run()
