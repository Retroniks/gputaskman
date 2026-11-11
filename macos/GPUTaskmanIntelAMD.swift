import SwiftUI
import AppKit
import Foundation

struct GPUProcess: Identifiable {
    let id: Int
    let name: String
    let cpu: Double?
    let gpu: Double?
    let vram: Double?
    let kind: String
    let gpuValueState: String
    let gpuAge: Double?
}
@MainActor final class GPUViewModel: ObservableObject {
    @Published var device = "AMD Radeon RX 580"
    @Published var total: Double?
    @Published var used: Double?
    @Published var vramState = "unavailable"
    @Published var vramAge: Double?
    @Published var gpuLoad: Double?
    @Published var items: [GPUProcess] = []
    @Published var status = "GPU-Messung wird gestartet …"
    @Published var updated: Date?
    @Published var count = 0
    @Published var observedCount = 0
    @Published var lastValueCount = 0
    @Published var activeGPUCount = 0
    @Published var topGPUText = "Keine GPU-Aktivität gemessen"
    private var worker: Process?
    private var reader: DispatchWorkItem?
    private var watchdog: Timer?
    private var lastError = ""
    private let source = "/Users/sysop/Projects/gputaskman/Source"

    func start() {
        guard worker == nil else { return }
        let process = Process()
        process.executableURL = URL(fileURLWithPath: source + "/.venv/bin/python")
        process.arguments = ["-u", source + "/macos/gpu_stream.py"]
        process.currentDirectoryURL = URL(fileURLWithPath: source)
        let stdout = Pipe(), stderr = Pipe()
        process.standardOutput = stdout
        process.standardError = stderr
        process.terminationHandler = { [weak self] p in
            Task { @MainActor [weak self] in
                guard let self = self, self.worker === p else { return }
                self.worker = nil
                self.status = "GPU-Sampler beendet (Code \(p.terminationStatus)). \(self.lastError)"
            }
        }
        do {
            try process.run()
            worker = process
        } catch {
            status = "Start fehlgeschlagen: \(error.localizedDescription)"
            return
        }
        let outHandle = stdout.fileHandleForReading
        let errHandle = stderr.fileHandleForReading
        DispatchQueue.global(qos: .utility).async { [weak self] in
            var pending = Data()
            while true {
                let chunk = outHandle.availableData
                if chunk.isEmpty { break }
                pending.append(chunk)
                while let newline = pending.firstIndex(of: 10) {
                    let line = pending.prefix(upTo: newline)
                    pending.removeSubrange(...newline)
                    if let obj = try? JSONSerialization.jsonObject(with: Data(line)) as? [String: Any] {
                        Task { @MainActor [weak self] in self?.receive(obj) }
                    }
                    if pending.count > 4_000_000 { pending.removeAll() }
                }
            }
        }
        DispatchQueue.global(qos: .utility).async { [weak self] in
            let errorData = errHandle.readDataToEndOfFile()
            let msg = String(data: errorData.suffix(1200), encoding: .utf8) ?? ""
            Task { @MainActor [weak self] in self?.lastError = msg }
        }
        watchdog = Timer.scheduledTimer(withTimeInterval: 2, repeats: true) { [weak self] _ in
            Task { @MainActor [weak self] in
                guard let self = self else { return }
                if let t = self.updated, Date().timeIntervalSince(t) > 12 {
                    self.status = "Messwerte verzögert – letzte Aktualisierung vor \(Int(Date().timeIntervalSince(t))) s"
                }
            }
        }
    }
    func restart() {
        watchdog?.invalidate()
        watchdog = nil
        worker?.terminate()
        worker = nil
        status = "GPU-Sampler wird neu gestartet …"
        start()
    }
    func receive(_ root: [String: Any]) {
        let adapter = root["adapter"] as? [String: Any] ?? [:]
        device = adapter["name"] as? String ?? device
        total = (root["vram_total"] as? NSNumber)?.doubleValue
        used = (root["vram_used"] as? NSNumber)?.doubleValue
        vramState = root["vram_value_state"] as? String ?? "unavailable"
        vramAge = (root["vram_value_age_s"] as? NSNumber)?.doubleValue
        let dev = root["device"] as? [String: Any] ?? [:]
        gpuLoad = (dev["util_gpu"] as? NSNumber)?.doubleValue
        let rawRows = root["processes"] as? [[String: Any]] ?? []
        observedCount = root["os_process_count"] as? Int ?? rawRows.count
        lastValueCount = root["gpu_last_count"] as? Int ?? 0
        activeGPUCount = root["gpu_active_count"] as? Int ?? 0
        if let top = root["gpu_top_process"] as? [String: Any],
           let name = top["name"] as? String,
           let load = (top["gpu_pct"] as? NSNumber)?.doubleValue {
            topGPUText = "\(name) · " + String(format: "%.2f %%", load)
        } else {
            topGPUText = "Keine GPU-Aktivität gemessen"
        }
        items = rawRows.compactMap { row -> GPUProcess? in
            guard let pid = row["pid"] as? Int else { return nil }
            return GPUProcess(id: pid, name: row["name"] as? String ?? "PID \(pid)",
                              cpu: (row["cpu_pct"] as? NSNumber)?.doubleValue,
                              gpu: (row["gpu_pct"] as? NSNumber)?.doubleValue,
                              vram: (row["vram_bytes"] as? NSNumber)?.doubleValue,
                              kind: row["kind"] as? String ?? "",
                              gpuValueState: row["gpu_value_state"] as? String ?? "unavailable",
                              gpuAge: (row["gpu_value_age_s"] as? NSNumber)?.doubleValue)
        }.sorted {
            return ($0.gpu ?? -1, $0.vram ?? -1, $0.name) > ($1.gpu ?? -1, $1.vram ?? -1, $1.name)
        }
        count += 1
        updated = Date()
        status = "\(observedCount) laufende Prozesse · \(lastValueCount) letzte GPU-Messwerte · Probe \(count)"
    }
    deinit { worker?.terminate() }
}

struct GPUContentView: View {
    @ObservedObject var model: GPUViewModel
    @State private var visibility = 0
    @State private var sorting = 0
    private var visibleItems: [GPUProcess] {
        var rows = model.items.filter { p in
            switch visibility {
            case 1: return p.gpuValueState == "current" || p.gpuValueState == "last"
            case 2: return p.gpuValueState == "current" && (p.gpu ?? 0) > 0
            default: return true
            }
        }
        rows.sort { a, b in
            switch sorting {
            case 1: return (a.cpu ?? -1, a.name) > (b.cpu ?? -1, b.name)
            case 2: return (a.vram ?? -1, a.name) > (b.vram ?? -1, b.name)
            case 3: return a.name.localizedStandardCompare(b.name) == .orderedAscending
            default: return (a.gpu ?? -1, a.name) > (b.gpu ?? -1, b.name)
            }
        }
        return rows
    }
    private func gib(_ n: Double?) -> String {
        n.map { String(format: "%.2f GiB", $0 / 1073741824) } ?? "n/a"
    }
    private func pct(_ n: Double?) -> String {
        n.map { String(format: "%.1f %%", $0) } ?? "n/a"
    }
    private var ratio: Double {
        guard let t = model.total, let u = model.used, t > 0 else { return 0 }
        return min(max(u/t, 0), 1)
    }
    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack {
                VStack(alignment: .leading, spacing: 3) {
                    Text(model.device).font(.title2.bold())
                    Text("GPU Task Manager · macOS Intel / AMD").foregroundStyle(.secondary)
                }
                Spacer()
                Button("Sampler neu starten") { model.restart() }
            }
            HStack(spacing: 24) {
                VStack(alignment: .leading) {
                    Text("GPU-Auslastung").foregroundStyle(.secondary)
                    Text(pct(model.gpuLoad)).font(.title2.monospacedDigit())
                }.frame(width: 150, alignment: .leading)
                VStack(alignment: .leading, spacing: 4) {
                    Text("Grafikspeicher").foregroundStyle(.secondary)
                    Text("\(gib(model.used)) / \(gib(model.total))").font(.title3.monospacedDigit())
                    ProgressView(value: ratio)
                    if model.vramState == "last" {
                        Text("Letzter gemessener Wert · vor \(Int(model.vramAge ?? 0)) s")
                            .font(.caption).foregroundStyle(.secondary)
                    } else if model.vramState == "unavailable" {
                        Text("VRAM-Messung noch nicht verfügbar")
                            .font(.caption).foregroundStyle(.secondary)
                    }
                    Text("GPU-Gesamtbelegung inkl. System/Treiber; keine Summe der App-Werte")
                        .font(.caption2).foregroundStyle(.secondary)
                }
                Spacer()
                VStack(alignment: .leading, spacing: 4) {
                    Text("GPU-aktive Apps").foregroundStyle(.secondary)
                    Text("\(model.activeGPUCount)").font(.title2.monospacedDigit())
                    Text(model.topGPUText).font(.caption).lineLimit(1)
                }.frame(maxWidth: 260, alignment: .leading)
                Spacer()
                VStack(alignment: .trailing) {
                    Text("Laufende Prozesse").foregroundStyle(.secondary)
                    Text("\(model.observedCount)").font(.title2.monospacedDigit())
                }
            }.padding(12).background(.quaternary.opacity(0.25), in: RoundedRectangle(cornerRadius: 10))
            HStack(spacing: 12) {
                Picker("Anzeigen", selection: $visibility) {
                    Text("Alle laufenden").tag(0)
                    Text("Mit GPU-Daten").tag(1)
                    Text("GPU aktiv").tag(2)
                }.pickerStyle(.segmented).frame(maxWidth: 470)
                Spacer()
                Picker("Sortieren", selection: $sorting) {
                    Text("GPU").tag(0)
                    Text("CPU").tag(1)
                    Text("Grafikspeicher").tag(2)
                    Text("Name").tag(3)
                }.frame(width: 205)
            }
            Table(visibleItems) {
                TableColumn("Prozess") { p in
                    HStack {
                        Image(nsImage: NSRunningApplication(processIdentifier: pid_t(p.id))?.icon ?? NSImage(systemSymbolName: "app", accessibilityDescription: nil)!)
                            .resizable().frame(width: 16, height: 16)
                        Text(p.name).lineLimit(1)
                    }
                }.width(min: 180, ideal: 260)
                TableColumn("PID") { p in Text("\(p.id)").monospacedDigit() }.width(65)
                TableColumn("CPU") { p in Text(pct(p.cpu)).monospacedDigit() }.width(80)
                TableColumn("GPU") { p in Text(pct(p.gpu)).monospacedDigit() }.width(80)
                TableColumn("Grafikspeicher") { p in
                    Text(gib(p.vram)).monospacedDigit()
                        .foregroundStyle(p.gpuValueState == "last" ? .secondary : .primary)
                }.width(125)
                TableColumn("GPU-Daten") { p in
                    Text(p.gpuValueState == "current" ? "Aktuell" :
                         p.gpuValueState == "last" ? "Letzter Wert" : "Nicht verfügbar")
                        .foregroundStyle(p.gpuValueState == "current" ? .primary : .secondary)
                        .help(p.gpuValueState == "last" ?
                              "Letzter tatsächlich gemessener GPU-Wert vor \(Int(p.gpuAge ?? 0)) Sekunden" :
                              "Nicht alle GPU-Speicherbelegungen können einzelnen Apps zugeordnet werden")
                }.width(120)
                TableColumn("Typ") { p in Text(p.kind).lineLimit(1) }.width(95)
            }
            HStack {
                Text("\(visibleItems.count) angezeigt · " + model.status).foregroundStyle(.secondary)
                Spacer()
                Text(model.updated.map { "Stand: " + $0.formatted(date: .omitted, time: .standard) } ?? "Noch keine Messung")
                    .foregroundStyle(.secondary)
            }.font(.caption)
        }
        .padding(18)
        .frame(minWidth: 1040, minHeight: 560)
        .onAppear { model.start() }
    }
}

@main struct GPUTaskmanIntelAMDApp: App {
    @StateObject private var model = GPUViewModel()
    var body: some Scene {
        WindowGroup("GPU Task Manager") { GPUContentView(model: model) }
        MenuBarExtra("GPU", systemImage: "cpu") {
            VStack(alignment: .leading, spacing: 9) {
                Text(model.device).font(.headline)
                Text("GPU: " + (model.gpuLoad.map { String(format: "%.1f %%", $0) } ?? "n/a"))
                Text("VRAM: " + (model.used.map { String(format: "%.2f GiB", $0 / 1073741824) } ?? "n/a"))
                Text("GPU-aktive Apps: \(model.activeGPUCount)")
                Text(model.topGPUText).font(.caption)
                Text(model.status).font(.caption).foregroundStyle(.secondary)
                Button("Sampler neu starten") { model.restart() }
            }.padding(10).frame(width: 290)
            .onAppear { model.start() }
        }
    }
}
