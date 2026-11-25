import SwiftUI
import AppKit
import Foundation

struct GPUProcess: Identifiable {
    let id: Int
    let name: String
    let cpu: Double?
    let gpu: Double?
    let graphicsFootprint: Double?
    let graphicsMap: Double?
    let graphicsChange: Double?
    let graphicsPeak: Double?
    let graphicsTrendSamples: Int
    let iosurface: Double?
    let ioaccelerator: Double?
    let graphicsMapAge: Double?
    let graphicsMapStatus: String
    let gpuClientObserved: Bool
    let footprintStatus: String
    let runtime: String
    let inside: String
    let modelFiles: [String]
    let llmModels: [String]
    let engineSummary: String
    let dedicatedVRAM: Double?
    let spill: Double?
    let paged: Double?
    let committed: Double?
    var footprintStatusLabel: String {
        switch footprintStatus {
        case "measured": return "Gemessen"
        case "last_measured": return "Letzter Wert"
        case "other_user": return "Zugriff fehlt"
        case "no_graphics_categories": return "Grafikzähler fehlen"
        case "footprint_no_json": return "Keine Prozessdaten"
        case "footprint_pid_missing": return "PID nicht im Report"
        case "footprint_timeout": return "Messung zu langsam"
        case "footprint_read_error": return "Messfehler"
        case "owner_unavailable": return "Besitzer unbekannt"
        case "not_targeted": return "Noch nicht geprüft"
        case "pending": return "Messung ausstehend"
        case "not_gpu_client": return "Kein GPU-Client"
        default: return "Noch nicht verfügbar"
        }
    }
    let kind: String
    let gpuValueState: String
    let gpuAge: Double?
    // Lexically sortable fixed-width keys preserve numeric order in native Table headers.
    var pidKey: String { String(format: "%010d", id) }
    var cpuKey: String { String(format: "%020.6f", cpu ?? -1) }
    var gpuKey: String { String(format: "%020.6f", gpu ?? -1) }
    var graphicsFootprintKey: String { String(format: "%020.0f", graphicsFootprint ?? -1) }
    var graphicsMapKey: String { String(format: "%020.0f", graphicsMap ?? -1) }
    var graphicsChangeKey: String { String(format: "%020.0f", (graphicsChange ?? -10000000000000) + 10000000000000) }
    var graphicsPeakKey: String { String(format: "%020.0f", graphicsPeak ?? -1) }
    var iosurfaceKey: String { String(format: "%020.0f", iosurface ?? -1) }
    var ioacceleratorKey: String { String(format: "%020.0f", ioaccelerator ?? -1) }

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
    @Published var gpuHistory: [Double?] = []
    @Published var vramHistory: [Double?] = []
    @Published var topConsumers: [GPUProcess] = []
    @Published var currentGPUClients = 0
    @Published var deviceTemperature: Double?
    @Published var devicePower: Double?
    @Published var deviceClock: Double?
    @Published var measuredGraphicsClients = 0
    @Published var graphicsMapMeasuredCount = 0
    @Published var graphicsMapOwnCount = 0
    @Published var graphicsMapNoCategoriesCount = 0
    @Published var graphicsMapErrorCount = 0
    @Published var graphicsMapPendingCount = 0
    @Published var nonzeroGraphicsClients = 0
    @Published var memoryMapPID: Int?
    @Published var memoryMapText = ""
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
        deviceTemperature = (dev["temp"] as? NSNumber)?.doubleValue
        devicePower = (dev["power_w"] as? NSNumber)?.doubleValue
        deviceClock = (dev["gfx_clock"] as? NSNumber)?.doubleValue
        gpuHistory.append(gpuLoad)
        if gpuHistory.count > 90 { gpuHistory.removeFirst(gpuHistory.count - 90) }
        vramHistory.append(vramState == "current" ? used.map { $0 / 1073741824 } : nil)
        if vramHistory.count > 90 { vramHistory.removeFirst(vramHistory.count - 90) }
        currentGPUClients = root["gpu_client_count"] as? Int ?? 0
        graphicsMapMeasuredCount = root["graphics_map_measured_count"] as? Int ?? 0
        graphicsMapOwnCount = root["graphics_map_own_gpu_count"] as? Int ?? 0
        let mapCoverage = root["graphics_map_coverage"] as? [String: Int] ?? [:]
        graphicsMapNoCategoriesCount = mapCoverage["no_graphics_categories"] ?? 0
        graphicsMapErrorCount = mapCoverage["errors"] ?? 0
        graphicsMapPendingCount = (mapCoverage["pending"] ?? 0) + (mapCoverage["stale"] ?? 0)
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
            let engines = row["engines"] as? [String: NSNumber] ?? [:]
            let enginesText = engines.keys.sorted().compactMap { key -> String? in
                guard let number = engines[key] else { return nil }
                return key + ": " + String(format: "%.1f %%", number.doubleValue)
            }.joined(separator: " · ")
            let runtimeNames = row["runtimes"] as? [String] ?? []
            let modelFiles = (row["model_files"] as? [[String: Any]] ?? [])
                .compactMap { $0["path"] as? String }
            let llm = row["llm"] as? [String: Any] ?? [:]
            let llmNames = (llm["models"] as? [[String: Any]] ?? [])
                .compactMap { ($0["name"] as? String) ?? ($0["label"] as? String) }
            return GPUProcess(id: pid, name: row["name"] as? String ?? "PID \(pid)",
                              cpu: (row["cpu_pct"] as? NSNumber)?.doubleValue,
                              gpu: (row["gpu_pct"] as? NSNumber)?.doubleValue,
                              graphicsFootprint: (row["graphics_footprint_bytes"] as? NSNumber)?.doubleValue,
                              graphicsMap: (row["graphics_map_bytes"] as? NSNumber)?.doubleValue,
                              graphicsChange: (row["graphics_change_bytes"] as? NSNumber)?.doubleValue,
                              graphicsPeak: (row["graphics_peak_5m_bytes"] as? NSNumber)?.doubleValue,
                              graphicsTrendSamples: row["graphics_trend_samples"] as? Int ?? 0,
                              iosurface: (row["iosurface_bytes"] as? NSNumber)?.doubleValue,
                              ioaccelerator: (row["ioaccelerator_bytes"] as? NSNumber)?.doubleValue,
                              graphicsMapAge: (row["graphics_map_age_s"] as? NSNumber)?.doubleValue,
                              graphicsMapStatus: row["graphics_map_status"] as? String ?? "pending",
                              gpuClientObserved: row["gpu_client_observed"] as? Bool ?? false,
                              footprintStatus: row["graphics_footprint_status"] as? String ?? "pending",
                              runtime: runtimeNames.joined(separator: " + "),
                              inside: row["inside"] as? String ?? "",
                              modelFiles: modelFiles,
                              llmModels: llmNames,
                              engineSummary: enginesText,
                              dedicatedVRAM: (row["dedicated_vram_bytes"] as? NSNumber)?.doubleValue,
                              spill: (row["shared_bytes"] as? NSNumber)?.doubleValue,
                              paged: (row["paged_out_bytes"] as? NSNumber)?.doubleValue,
                              committed: (row["committed_bytes"] as? NSNumber)?.doubleValue,
                              kind: row["kind"] as? String ?? "",
                              gpuValueState: row["gpu_value_state"] as? String ?? "unavailable",
                              gpuAge: (row["gpu_value_age_s"] as? NSNumber)?.doubleValue)
        }.sorted {
            return ($0.graphicsFootprint ?? -1, $0.gpu ?? -1, $0.name) >
                   ($1.graphicsFootprint ?? -1, $1.gpu ?? -1, $1.name)
        }
        measuredGraphicsClients = items.filter { $0.gpuClientObserved && $0.graphicsFootprint != nil }.count
        nonzeroGraphicsClients = items.filter { $0.gpuClientObserved && ($0.graphicsFootprint ?? 0) > 0 }.count
        topConsumers = items.filter { $0.gpuClientObserved && ($0.graphicsFootprint ?? 0) > 0 }
            .sorted { ($0.graphicsFootprint ?? 0) > ($1.graphicsFootprint ?? 0) }
        if topConsumers.count > 5 { topConsumers = Array(topConsumers.prefix(5)) }
        count += 1
        updated = Date()
        status = "\(observedCount) laufende Prozesse · \(lastValueCount) letzte GPU-Messwerte · Probe \(count)"
    }
    func loadMemoryMap(pid: Int) {
        memoryMapPID = pid
        memoryMapText = "Lese echte footprint- und vmmap-Kategorien für PID \(pid) …"
        let executable = source + "/.venv/bin/python"
        let helper = source + "/macos/gpu_memory_map_040.py"
        let workingDirectory = source
        DispatchQueue.global(qos: .utility).async { [weak self] in
            let process = Process()
            process.executableURL = URL(fileURLWithPath: executable)
            process.arguments = [helper, "--pid", String(pid)]
            process.currentDirectoryURL = URL(fileURLWithPath: workingDirectory)
            let pipe = Pipe()
            process.standardOutput = pipe
            process.standardError = pipe
            var result = "Memory-Map nicht verfügbar"
            do {
                try process.run()
                let data = pipe.fileHandleForReading.readDataToEndOfFile()
                process.waitUntilExit()
                result = String(data: data, encoding: .utf8) ?? "Ausgabe nicht lesbar"
                if process.terminationStatus != 0 {
                    result += "\nStatus: Messung fehlgeschlagen, Exit \(process.terminationStatus)"
                }
            } catch {
                result = "Memory-Map konnte nicht gestartet werden: \(error.localizedDescription)"
            }
            let outcome = result
            Task { @MainActor [weak self] in
                guard let self = self, self.memoryMapPID == pid else { return }
                self.memoryMapText = outcome
            }
        }
    }
    deinit { worker?.terminate() }
}

struct GPUHistoryPanel: View {
    let title: String
    let values: [Double?]
    let limit: Double
    let suffix: String
    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Text(title).font(.caption).foregroundStyle(.secondary)
                Spacer()
                Text(values.last.flatMap { $0 }.map { String(format: "%.1f%@", $0, suffix) } ?? "—")
                    .font(.caption.monospacedDigit())
            }
            GeometryReader { frame in
                Path { path in
                    let count = max(values.count - 1, 1)
                    var connected = false
                    for (i, item) in values.enumerated() {
                        guard let value = item else { connected = false; continue }
                        let x = frame.size.width * CGFloat(i) / CGFloat(count)
                        let fraction = min(max(value / max(limit, 0.001), 0.0), 1.0)
                        let y = frame.size.height * (1 - CGFloat(fraction))
                        if connected { path.addLine(to: CGPoint(x: x, y: y)) }
                        else { path.move(to: CGPoint(x: x, y: y)); connected = true }
                    }
                }
                .stroke(Color.accentColor, style: StrokeStyle(lineWidth: 1.8, lineCap: .round, lineJoin: .round))
            }
            .frame(height: 44)
            .background(.quaternary.opacity(0.16), in: RoundedRectangle(cornerRadius: 4))
        }
    }
}

struct GPUContentView: View {
    @ObservedObject var model: GPUViewModel
    @State private var visibility = 1
    @State private var searchText = ""
    @State private var selectedPIDs: Set<Int> = []
    @State private var sortOrder = [KeyPathComparator(\GPUProcess.graphicsFootprintKey, order: .reverse)]
    private var visibleItems: [GPUProcess] {
        let query = searchText.trimmingCharacters(in: .whitespacesAndNewlines)
        var rows = model.items.filter { p in
            if !query.isEmpty && !p.name.localizedCaseInsensitiveContains(query)
               && !String(p.id).contains(query) { return false }
            switch visibility {
            case 1: return p.gpuValueState == "current" || p.gpuValueState == "last"
            case 2: return p.gpuValueState == "current" && (p.gpu ?? 0) > 0
            case 3: return p.graphicsMapStatus == "measured" && p.graphicsMap != nil
            case 4: return p.graphicsMapStatus == "no_graphics_categories"
            default: return true
            }
        }
        rows.sort(using: sortOrder)
        return rows
    }
    private func gib(_ n: Double?) -> String {
        guard let number = n, number >= 0 else { return "—" }
        if number < 107374182.4 { return String(format: "%.1f MiB", number / 1048576) }
        return String(format: "%.2f GiB", number / 1073741824)
    }
    private func changeText(_ value: Double?) -> String {
        guard let number = value else { return "—" }
        if number == 0 { return "0 KiB" }
        if abs(number) < 1048576 { return String(format: "%+.0f KiB", number / 1024) }
        return String(format: "%+.2f MiB", number / 1048576)
    }
    private func pct(_ n: Double?) -> String {
        n.map { String(format: "%.1f %%", $0) } ?? "—"
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
                    Text("GPU-Monitor").foregroundStyle(.secondary)
                }
                Spacer()
                Button("Messung neu starten") { model.restart() }
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
                    Text(model.vramState == "current"
                         ? "Gesamt-VRAM: gültiger Gerätewert. Kein dedizierter VRAM je PID."
                         : "Gesamt-VRAM: kein aktueller gültiger Gerätewert. Kein dedizierter VRAM je PID.")
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
                VStack(alignment: .leading, spacing: 3) {
                    Text("GPU-PROZESSE · \(model.currentGPUClients) GPU-Clients · Grafik-Map \(model.graphicsMapMeasuredCount)/\(model.graphicsMapOwnCount) eigene")
                        .font(.headline)
                    Text("Ohne Grafik-Kategorie: \(model.graphicsMapNoCategoriesCount) · Abfragefehler: \(model.graphicsMapErrorCount) · Ausstehend/veraltet: \(model.graphicsMapPendingCount)")
                        .font(.caption).foregroundStyle(.secondary)
                }
                Spacer()
                if let temperature = model.deviceTemperature {
                    Text(String(format: "GPU %.0f °C", temperature))
                }
                if let power = model.devicePower {
                    Text(String(format: "%.0f W", power))
                }
                if let clock = model.deviceClock {
                    Text(String(format: "%.0f MHz", clock))
                }
                Text("VRAM je PID nur mit belegtem Treiberzähler")
                    .foregroundStyle(.secondary)
            }.font(.caption)
            HStack(spacing: 12) {
                Picker("Anzeigen", selection: $visibility) {
                    Text("Alle laufenden").tag(0)
                    Text("Mit GPU-Daten").tag(1)
                    Text("GPU aktiv").tag(2)
                    Text("Grafikwerte").tag(3)
                    Text("Ohne Grafik").tag(4)
                }.pickerStyle(.segmented).frame(maxWidth: 650)
                Spacer()
                TextField("Prozess oder PID suchen", text: $searchText)
                    .textFieldStyle(.roundedBorder)
                    .frame(width: 265)
                    .accessibilityLabel("Prozess oder PID suchen")
            }
            Table(visibleItems, selection: $selectedPIDs, sortOrder: $sortOrder) {
                TableColumn("Prozess", value: \GPUProcess.name) { p in
                    HStack {
                        Image(nsImage: NSRunningApplication(processIdentifier: pid_t(p.id))?.icon ?? NSImage(systemSymbolName: "app", accessibilityDescription: nil)!)
                            .resizable().frame(width: 16, height: 16)
                        Text(p.name).lineLimit(1)
                    }
                }.width(min: 170, ideal: 215)
                TableColumn("PID", value: \GPUProcess.pidKey) { p in
                    Text(String(p.id)).monospacedDigit()
                }.width(65)
                TableColumn("Typ") { p in Text(p.kind).lineLimit(1) }.width(90)
                TableColumn("Runtime", value: \GPUProcess.runtime) { p in
                    Text(p.runtime.isEmpty ? "—" : p.runtime).lineLimit(1)
                }.width(min: 85, ideal: 125)
                TableColumn("IOSurface", value: \GPUProcess.iosurfaceKey) { p in
                    Text(gib(p.iosurface)).monospacedDigit()
                        .help("macOS-Hostspeicher: IOSurface dirty. Kein dedizierter RX-580-VRAM.")
                }.width(105)
                TableColumn("IOAccelerator", value: \GPUProcess.ioacceleratorKey) { p in
                    Text(gib(p.ioaccelerator)).monospacedDigit()
                        .help("macOS-Hostspeicher: IOAccelerator dirty. Kein dedizierter RX-580-VRAM.")
                }.width(116)
                TableColumn("GPU", value: \GPUProcess.gpuKey) { p in
                    Text(pct(p.gpu)).monospacedDigit()
                }.width(70)
                TableColumn("Grafik-dirty", value: \GPUProcess.graphicsMapKey) { p in
                    Text(gib(p.graphicsMap)).monospacedDigit()
                        .help("Summe der ausgewiesenen Grafik-Kategorien aus footprint; keine Radeon-VRAM-Zuordnung. Status: " + p.graphicsMapStatus)
                }.width(110)
                 TableColumn("Δ / Peak 5 Min", value: \GPUProcess.graphicsPeakKey) { p in
                    Text(changeText(p.graphicsChange) + " / " + gib(p.graphicsPeak))
                        .monospacedDigit()
                        .help("Links: Änderung seit letzter echter footprint-Messung; rechts: höchster Grafik-dirty-Wert in fünf Minuten; sortiert nach Peak")
                }.width(198)
                TableColumn("Inside", value: \GPUProcess.inside) { p in
                    Text(p.inside.isEmpty ? "—" : p.inside).lineLimit(1)
                }.width(min: 130, ideal: 210)
            }
            if let pid = selectedPIDs.first,
               let process = model.items.first(where: { $0.id == pid }) {
                VStack(alignment: .leading, spacing: 6) {
                    HStack(alignment: .firstTextBaseline, spacing: 16) {
                        Text(process.name).font(.headline).lineLimit(1)
                        Text("PID \(process.id) · \(process.kind)").foregroundStyle(.secondary)
                        Spacer()
                        Text("GPU " + pct(process.gpu)).monospacedDigit()
                        Text("VRAM " + gib(process.dedicatedVRAM)).monospacedDigit()
                        Text("Grafik-RAM " + gib(process.graphicsFootprint)).monospacedDigit()
                        Button("PID kopieren") {
                            NSPasteboard.general.clearContents()
                            NSPasteboard.general.setString(String(process.id), forType: .string)
                        }
                        Button("Memory-Map") { model.loadMemoryMap(pid: pid) }
                    }
                    HStack(spacing: 15) {
                        Text("IOSurface dirty: " + gib(process.iosurface))
                        Text("IOAccelerator dirty: " + gib(process.ioaccelerator))
                        Text("Grafik-dirty: " + gib(process.graphicsMap))
                        Text("Δ letzte Messung: " + changeText(process.graphicsChange))
                        Text("Peak 5 Min: " + gib(process.graphicsPeak))
                        Text("Memory-Map: " + (process.graphicsMapStatus == "pending" ? "ausstehend" : process.graphicsMapStatus))
                        if let age = process.graphicsMapAge {
                            Text(String(format: "vor %.0f s", age))
                        }
                    }.font(.caption).monospacedDigit()
                    Text("Grafik-Kategorien: macOS-Hostspeicher; keine dedizierte RX-580-VRAM-Zuordnung")
                        .font(.caption2).foregroundStyle(.secondary)
                    Text("Runtime: " + (process.runtime.isEmpty ? "Nicht ermittelt" : process.runtime))
                        .font(.caption)
                    Text("Inside: " + (process.inside.isEmpty ? "Nicht ermittelt" : process.inside))
                        .font(.caption).lineLimit(2)
                    if !process.llmModels.isEmpty {
                        Text("Erkannte Modelle: " + process.llmModels.prefix(3).joined(separator: ", "))
                            .font(.caption).lineLimit(2)
                    } else if !process.modelFiles.isEmpty {
                        Text("Modell-Dateien: " + process.modelFiles.prefix(3).map {
                            URL(fileURLWithPath: $0).lastPathComponent
                        }.joined(separator: ", "))
                            .font(.caption).lineLimit(2)
                    }
                    HStack(spacing: 18) {
                        Text("GPU-Engines: " + (process.engineSummary.isEmpty ? "Keine separaten Zähler" : process.engineSummary))
                        Text("Spill: " + gib(process.spill))
                        Text("Paged: " + gib(process.paged))
                        Text("Commit: " + gib(process.committed))
                        Text("Speicherstatus: " + process.footprintStatusLabel)
                    }.font(.caption).foregroundStyle(.secondary)
                    Text("Modell-/Runtime-Erkennung belegt keine VRAM-Residency. Unverfügbare Zähler bleiben —.")
                        .font(.caption2).foregroundStyle(.secondary)
                    if model.memoryMapPID == pid {
                        ScrollView([.vertical, .horizontal]) {
                            Text(model.memoryMapText)
                                .font(.system(size: 11, design: .monospaced))
                                .textSelection(.enabled)
                                .frame(maxWidth: .infinity, alignment: .leading)
                        }
                        .frame(height: 220)
                        .background(.quaternary.opacity(0.12))
                    }
                }.padding(10)
                 .background(.quaternary.opacity(0.24), in: RoundedRectangle(cornerRadius: 8))
            }
            HStack {
                Text("\(visibleItems.count) angezeigt · \(model.nonzeroGraphicsClients) positive Grafik-Messwerte · kein dedizierter VRAM je PID")
                    .foregroundStyle(.secondary)
                Spacer()
                Text(model.updated.map { "Stand: " + $0.formatted(date: .omitted, time: .standard) } ?? "Noch keine Messung")
                    .foregroundStyle(.secondary)
            }.font(.caption)
        }
        .padding(18)
        .frame(minWidth: 1480, minHeight: 650)
        .onAppear {
            model.start()
            NSApp.activate(ignoringOtherApps: true)
        }
    }
}

private struct GPUMenuPanel: View {
    @Environment(\.openWindow) private var openWindow
    @ObservedObject var model: GPUViewModel

    var body: some View {
        VStack(alignment: .leading, spacing: 9) {
            Button("Hauptfenster öffnen") {
                openWindow(id: "main")
                NSApp.activate(ignoringOtherApps: true)
            }
            Divider()
            Text(model.device).font(.headline)
            Text("GPU: " + (model.gpuLoad.map { String(format: "%.1f %%", $0) } ?? "—"))
            Text("VRAM: " + (model.used.map { String(format: "%.2f GiB", $0 / 1073741824) } ?? "—"))
            Text("GPU-aktive Apps: \(model.activeGPUCount)")
            Text(model.topGPUText).font(.caption)
            Text(model.status).font(.caption).foregroundStyle(.secondary)
            Button("Messung neu starten") { model.restart() }
        }
        .padding(10).frame(width: 290)
        .onAppear { model.start() }
    }
}

@main struct GPUTaskmanIntelAMDApp: App {
    @StateObject private var model = GPUViewModel()
    var body: some Scene {
        WindowGroup("GPU-Monitor", id: "main") { GPUContentView(model: model) }
        MenuBarExtra("GPU", systemImage: "cpu") {
            GPUMenuPanel(model: model)
        }
    }
}
