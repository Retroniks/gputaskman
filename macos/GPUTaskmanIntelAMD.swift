import SwiftUI
import Foundation

struct GPUProcess: Identifiable {
    let id: Int
    let name: String
    let cpu: Double?
    let gpu: Double?
    let vram: Double?
}

@MainActor final class GPUViewModel: ObservableObject {
    @Published var device = "AMD Radeon RX 580"
    @Published var total: Double = 0
    @Published var used: Double = 0
    @Published var items: [GPUProcess] = []
    @Published var status = "Daten werden geladen …"
    @Published var updated: Date?
    private var refreshing = false
    private var timer: Timer?

    func start() {
        guard timer == nil else { return }
        refresh()
        timer = Timer.scheduledTimer(withTimeInterval: 12, repeats: true) { [weak self] _ in
            Task { @MainActor in self?.refresh() }
        }
    }
    func refresh() {
        guard !refreshing else { return }
        refreshing = true
        let python = "/Users/sysop/Projects/gputaskman/Source/.venv/bin/python"
        DispatchQueue.global(qos: .utility).async {
            let process = Process()
            process.executableURL = URL(fileURLWithPath: python)
            process.arguments = ["-m", "gputaskman", "--json"]
            process.currentDirectoryURL = URL(fileURLWithPath: "/Users/sysop/Projects/gputaskman/Source")
            let output = Pipe()
            process.standardOutput = output
            process.standardError = Pipe()
            do {
                try process.run()
                let data = output.fileHandleForReading.readDataToEndOfFile()
                process.waitUntilExit()
                guard process.terminationStatus == 0 else { throw NSError(domain: "GPU", code: Int(process.terminationStatus)) }
                guard let root = try JSONSerialization.jsonObject(with: data) as? [String: Any] else { throw NSError(domain: "GPU", code: 2) }
                let adapter = root["adapter"] as? [String: Any] ?? [:]
                let deviceName = adapter["name"] as? String ?? "Unbekannte GPU"
                let total = (root["vram_total"] as? NSNumber)?.doubleValue ?? 0
                let used = (root["vram_used"] as? NSNumber)?.doubleValue ?? 0
                let rows = (root["processes"] as? [[String: Any]] ?? []).compactMap { row -> GPUProcess? in
                    guard let pid = row["pid"] as? Int else { return nil }
                    return GPUProcess(id: pid, name: row["name"] as? String ?? "PID \(pid)",
                                      cpu: (row["cpu_pct"] as? NSNumber)?.doubleValue,
                                      gpu: (row["gpu_pct"] as? NSNumber)?.doubleValue,
                                      vram: (row["vram_bytes"] as? NSNumber)?.doubleValue)
                }.sorted { ($0.gpu ?? 0) > ($1.gpu ?? 0) }
                DispatchQueue.main.async {
                    self.device = deviceName
                    self.total = total
                    self.used = used
                    self.items = rows
                    self.updated = Date()
                    self.status = "\(rows.count) Prozesse · Livewerte"
                    self.refreshing = false
                }
            } catch {
                DispatchQueue.main.async {
                    self.status = "Messung fehlgeschlagen: \(error.localizedDescription)"
                    self.refreshing = false
                }
            }
        }
    }
}

struct GPUContentView: View {
    @ObservedObject var model: GPUViewModel
    private func bytes(_ value: Double) -> String { String(format: "%.2f GiB", value / 1073741824) }
    private func pct(_ value: Double?) -> String { value.map { String(format: "%.1f %%", $0) } ?? "n/a" }
    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack {
                VStack(alignment: .leading) {
                    Text(model.device).font(.title2.bold())
                    Text("macOS Intel · AMD GPU Monitor").foregroundStyle(.secondary)
                }
                Spacer()
                Button("Aktualisieren") { model.refresh() }
            }
            HStack {
                VStack(alignment: .leading) {
                    Text("VRAM verwendet").font(.headline)
                    Text("\(bytes(model.used)) / \(bytes(model.total))").monospacedDigit()
                }
                Spacer()
                ProgressView(value: model.total > 0 ? min(model.used/model.total, 1) : 0).frame(width: 220)
            }
            HStack {
                Text("Prozess").frame(maxWidth: .infinity, alignment: .leading)
                Text("PID").frame(width: 75, alignment: .trailing)
                Text("CPU").frame(width: 80, alignment: .trailing)
                Text("GPU").frame(width: 80, alignment: .trailing)
                Text("Grafikspeicher").frame(width: 115, alignment: .trailing)
            }.font(.headline)
            Divider()
            List(model.items) { item in
                HStack {
                    Text(item.name).lineLimit(1).frame(maxWidth: .infinity, alignment: .leading)
                    Text(String(item.id)).frame(width: 75, alignment: .trailing)
                    Text(pct(item.cpu)).frame(width: 80, alignment: .trailing)
                    Text(pct(item.gpu)).frame(width: 80, alignment: .trailing)
                    Text(item.vram.map { bytes($0) } ?? "n/a").frame(width: 115, alignment: .trailing)
                }.monospacedDigit()
            }
            Text(model.status).foregroundStyle(.secondary).font(.caption)
        }
        .padding(20)
        .frame(minWidth: 840, minHeight: 500)
        .onAppear { model.start() }
    }
}

@main struct GPUTaskmanIntelAMDApp: App {
    @StateObject private var model = GPUViewModel()
    var body: some Scene {
        WindowGroup("GPU Task Manager") { GPUContentView(model: model) }
        MenuBarExtra("GPU", systemImage: "cpu") {
            VStack(alignment: .leading, spacing: 8) {
                Text(model.device).font(.headline)
                Text("VRAM: \(String(format: "%.2f / %.2f GiB", model.used / 1073741824, model.total / 1073741824))")
                Text(model.status)
                Button("Aktualisieren") { model.refresh() }
            }.padding(10).frame(width: 265)
        }
    }
}
