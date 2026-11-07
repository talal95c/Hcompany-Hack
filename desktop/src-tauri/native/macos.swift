import AppKit
import AVFoundation
import ApplicationServices
import ScreenCaptureKit

@main
struct Native {
    static func json(_ value: Any) throws {
        FileHandle.standardOutput.write(try JSONSerialization.data(withJSONObject: value))
    }

    static func main() async {
        do {
            let args = Array(CommandLine.arguments.dropFirst())
            switch args.first {
            case "permissions":
                try json(["screen": CGPreflightScreenCaptureAccess(),
                          "accessibility": AXIsProcessTrusted(),
                          "microphone": AVCaptureDevice.authorizationStatus(for: .audio) == .authorized])
            case "request":
                guard args.count == 2 else { throw Failure.invalid }
                switch args[1] {
                case "screen": _ = CGRequestScreenCaptureAccess()
                case "accessibility":
                    let options = [kAXTrustedCheckOptionPrompt.takeUnretainedValue() as String: true]
                    _ = AXIsProcessTrustedWithOptions(options as CFDictionary)
                case "microphone": _ = await AVCaptureDevice.requestAccess(for: .audio)
                default: throw Failure.invalid
                }
            case "focus":
                let name = NSWorkspace.shared.frontmostApplication?.bundleIdentifier
                FileHandle.standardOutput.write(Data((name == "org.blenderfoundation.blender" ? "true" : "false").utf8))
            case "monitors":
                var ids = [CGDirectDisplayID](repeating: 0, count: 32)
                var count: UInt32 = 0
                guard CGGetActiveDisplayList(32, &ids, &count) == .success else { throw Failure.invalid }
                let values: [[String: Any]] = ids.prefix(Int(count)).map { id in
                    let frame = CGDisplayBounds(id)
                    let scale = Double(CGDisplayPixelsWide(id)) / frame.width
                    return ["id": String(id), "scale": scale,
                            "physical": ["x": frame.minX * scale, "y": frame.minY * scale,
                                         "width": Double(CGDisplayPixelsWide(id)), "height": Double(CGDisplayPixelsHigh(id))],
                            "logical_x": frame.minX, "logical_y": frame.minY]
                }
                try json(values)
            case "capture":
                if #available(macOS 14.0, *) { try await capture(args) }
                else { throw Failure.unsupported }
            default: throw Failure.invalid
            }
        } catch {
            FileHandle.standardError.write(Data("Native operation failed: \(error)".utf8))
            exit(1)
        }
    }

    @available(macOS 14.0, *)
    static func capture(_ args: [String]) async throws {
        guard args.count == 7, let pid = Int32(args[1]), let id = UInt32(args[2]),
              let x = Double(args[3]), let y = Double(args[4]),
              let width = Double(args[5]), let height = Double(args[6]) else {
            throw Failure.invalid
        }
        let content = try await SCShareableContent.excludingDesktopWindows(false, onScreenWindowsOnly: true)
        guard let display = content.displays.first(where: { $0.displayID == id }) else { throw Failure.invalid }
        let ownApps = content.applications.filter { $0.processID == pid }
        let ownWindows = content.windows.filter { $0.owningApplication?.processID == pid }
        guard !ownApps.isEmpty || !ownWindows.isEmpty else { throw Failure.noExclusion }
        let filter = ownApps.isEmpty
            ? SCContentFilter(display: display, excludingWindows: ownWindows)
            : SCContentFilter(display: display, excludingApplications: ownApps, exceptingWindows: [])
        let scale = Double(CGDisplayPixelsWide(id)) / CGDisplayBounds(id).width
        let config = SCStreamConfiguration()
        config.sourceRect = CGRect(x: x / scale, y: y / scale, width: width / scale, height: height / scale)
        config.width = Int(width)
        config.height = Int(height)
        config.showsCursor = false
        let image = try await SCScreenshotManager.captureImage(contentFilter: filter, configuration: config)
        let bitmap = NSBitmapImageRep(cgImage: image)
        guard let png = bitmap.representation(using: .png, properties: [:]) else { throw Failure.invalid }
        FileHandle.standardOutput.write(png)
    }

    enum Failure: Error { case invalid, unsupported, noExclusion }
}
