//
//  ContentView.swift
//  harmony-step1
//
//  Created by Rob Hughes on 12/5/25.
//

import SwiftUI
import PhotosUI
import UIKit

private enum OCRMode: String, CaseIterable, Identifiable {
    case tesseract = "ocr-tesseract"
    case easyocr = "ocr-easyocr"
    case fusion = "ocr-fusion"

    var id: String { rawValue }
    var label: String {
        switch self {
        case .tesseract: return "Tesseract"
        case .easyocr: return "EasyOCR"
        case .fusion: return "Fusion (default)"
        }
    }
}

private enum ModelChoice: String, CaseIterable, Identifiable {
    case gpt5Mini = "openai/gpt-5-mini"
    case gpt41Mini = "openai/gpt-4.1-mini"
    case geminiFlash = "google/gemini-2.5-flash"
    case grok41Fast = "xai/grok-4.1-fast-reasoning"
    case deepseek = "deepseek/deepseek-v3.2-thinking"

    var id: String { rawValue }
    var displayName: String {
        switch self {
        case .gpt5Mini: return "gpt-5-mini"
        case .gpt41Mini: return "gpt-4.1-mini"
        case .geminiFlash: return "gemini-2.5-flash"
        case .grok41Fast: return "grok-4.1-fast-reasoning"
        case .deepseek: return "deepseek-v3.2-thinking"
        }
    }
}

private enum HarmonyClientError: LocalizedError {
    case invalidURL
    case invalidResponse
    case server(status: Int, message: String)

    var errorDescription: String? {
        switch self {
        case .invalidURL:
            return "Server URL is invalid."
        case .invalidResponse:
            return "Unexpected response from server."
        case .server(let status, let message):
            return "Server error (\(status)): \(message)"
        }
    }
}

private enum JSONValue: Codable, CustomStringConvertible {
    case string(String)
    case number(Double)
    case bool(Bool)
    case object([String: JSONValue])
    case array([JSONValue])
    case null

    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if container.decodeNil() {
            self = .null
        } else if let value = try? container.decode(Bool.self) {
            self = .bool(value)
        } else if let value = try? container.decode(Double.self) {
            self = .number(value)
        } else if let value = try? container.decode(String.self) {
            self = .string(value)
        } else if let value = try? container.decode([String: JSONValue].self) {
            self = .object(value)
        } else if let value = try? container.decode([JSONValue].self) {
            self = .array(value)
        } else {
            throw DecodingError.dataCorrupted(
                .init(codingPath: decoder.codingPath, debugDescription: "Unsupported JSON value.")
            )
        }
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        switch self {
        case .string(let value):
            try container.encode(value)
        case .number(let value):
            try container.encode(value)
        case .bool(let value):
            try container.encode(value)
        case .object(let value):
            try container.encode(value)
        case .array(let value):
            try container.encode(value)
        case .null:
            try container.encodeNil()
        }
    }

    var description: String {
        switch self {
        case .string(let value):
            return value
        case .number(let value):
            return "\(value)"
        case .bool(let value):
            return value ? "true" : "false"
        case .object(let dict):
            let joined = dict
                .map { "\($0): \($1.description)" }
                .joined(separator: ", ")
            return "{\(joined)}"
        case .array(let values):
            let joined = values.map(\.description).joined(separator: ", ")
            return "[\(joined)]"
        case .null:
            return "null"
        }
    }

    func toAny() -> Any {
        switch self {
        case .string(let value):
            return value
        case .number(let value):
            return value
        case .bool(let value):
            return value
        case .object(let dict):
            return dict.mapValues { $0.toAny() }
        case .array(let values):
            return values.map { $0.toAny() }
        case .null:
            return NSNull()
        }
    }

    func prettyPrinted() -> String {
        let anyValue = toAny()
        if JSONSerialization.isValidJSONObject(anyValue),
           let data = try? JSONSerialization.data(withJSONObject: anyValue, options: [.prettyPrinted]),
           let pretty = String(data: data, encoding: .utf8) {
            return pretty
        }
        return description
    }
}

private struct ImageParseResponse: Decodable {
    let ocrText: String
    let event: JSONValue

    enum CodingKeys: String, CodingKey {
        case ocrText = "ocr_text"
        case event
    }
}

private struct HealthResponse: Decodable {
    let status: String
}

private struct HarmonyClient {
    let baseURL: URL

    init(baseURLString: String) throws {
        guard var components = URLComponents(string: baseURLString) else {
            throw HarmonyClientError.invalidURL
        }

        // Default to port 8000 for plain HTTP if none is provided.
        if components.scheme == "http", components.port == nil {
            components.port = 8000
        }

        guard let url = components.url else {
            throw HarmonyClientError.invalidURL
        }
        self.baseURL = url
    }
    
    private let longTimeoutSession: URLSession = {
        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest = 240   // 4 minutes
        config.timeoutIntervalForResource = 240  // 4 minutes
        return URLSession(configuration: config)
    }()

    func uploadImage(
        data: Data,
        modelString: String,
        ocrMode: OCRMode
    ) async throws -> ImageParseResponse {
        var components = URLComponents(url: baseURL, resolvingAgainstBaseURL: false)
        let trimmedPath = components?.path.trimmingCharacters(in: CharacterSet(charactersIn: "/")) ?? ""
        let baseComponents = trimmedPath.isEmpty ? [] : [trimmedPath]
        components?.path = "/" + (baseComponents + ["parse", "image"]).joined(separator: "/")
        components?.queryItems = [
            URLQueryItem(name: "ocr_mode", value: ocrMode.rawValue),
            URLQueryItem(name: "model_string", value: modelString)
        ]
        guard let url = components?.url else {
            throw HarmonyClientError.invalidURL
        }

        let boundary = "Boundary-\(UUID().uuidString)"
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.httpBody = makeMultipartBody(data: data, boundary: boundary)

        let (responseData, response) = try await self.longTimeoutSession.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse else {
            throw HarmonyClientError.invalidResponse
        }
        guard (200..<300).contains(httpResponse.statusCode) else {
            let message = String(data: responseData, encoding: .utf8) ?? "Unknown error"
            throw HarmonyClientError.server(status: httpResponse.statusCode, message: message)
        }

        let decoder = JSONDecoder()
        return try decoder.decode(ImageParseResponse.self, from: responseData)
    }

    func health() async throws -> String {
        var components = URLComponents(url: baseURL, resolvingAgainstBaseURL: false)
        let trimmedPath = components?.path.trimmingCharacters(in: CharacterSet(charactersIn: "/")) ?? ""
        let baseComponents = trimmedPath.isEmpty ? [] : [trimmedPath]
        components?.path = "/" + (baseComponents + ["health"]).joined(separator: "/")
        guard let url = components?.url else {
            throw HarmonyClientError.invalidURL
        }

        let (data, response) = try await URLSession.shared.data(from: url)
        guard let httpResponse = response as? HTTPURLResponse else {
            throw HarmonyClientError.invalidResponse
        }
        guard (200..<300).contains(httpResponse.statusCode) else {
            let message = String(data: data, encoding: .utf8) ?? "Unknown error"
            throw HarmonyClientError.server(status: httpResponse.statusCode, message: message)
        }

        let decoder = JSONDecoder()
        let result = try decoder.decode(HealthResponse.self, from: data)
        return result.status
    }

    private func makeMultipartBody(data: Data, boundary: String) -> Data {
        var body = Data()
        let lineBreak = "\r\n"
        body.append("--\(boundary)\(lineBreak)")
        body.append("Content-Disposition: form-data; name=\"file\"; filename=\"upload.jpg\"\(lineBreak)")
        body.append("Content-Type: image/jpeg\(lineBreak + lineBreak)")
        body.append(data)
        body.append(lineBreak)
        body.append("--\(boundary)--\(lineBreak)")
        return body
    }
}

private extension Data {
    mutating func append(_ string: String) {
        if let data = string.data(using: .utf8) {
            append(data)
        }
    }
}

struct ContentView: View {
    @State private var serverURLString = "https://api.harmo.nyc"
    @State private var selectedModel: ModelChoice = .geminiFlash
    @State private var selectedOCR: OCRMode = .fusion
    @State private var selectedItem: PhotosPickerItem?
    @State private var imagePreview: UIImage?
    @State private var imageData: Data?
    @State private var isSending = false
    @State private var statusText = "Pick an image to upload."
    @State private var responseText: String?
    @State private var errorText: String?
    @State private var isCheckingHealth = false
    @State private var healthText: String?

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    Text("Harmony OCR to Event")
                        .font(.title2.bold())

                    VStack(alignment: .leading, spacing: 8) {
                        Text("Server URL")
                            .font(.subheadline.bold())
                        TextField("http://localhost:8000", text: $serverURLString)
                            .keyboardType(.URL)
                            .textInputAutocapitalization(.never)
                            .autocorrectionDisabled()
                            .padding(10)
                            .background(Color(.secondarySystemBackground))
                            .cornerRadius(8)
                    }

                    VStack(alignment: .leading, spacing: 8) {
                        Text("Health")
                            .font(.subheadline.bold())
                        HStack {
                            Button {
                                checkHealth()
                            } label: {
                                HStack {
                                    if isCheckingHealth {
                                        ProgressView()
                                    }
                                    Text(isCheckingHealth ? "Checking..." : "Check Health")
                                }
                            }
                            .buttonStyle(.bordered)

                            if let healthText {
                                Text(healthText)
                                    .font(.footnote)
                                    .foregroundColor(.secondary)
                            }
                        }
                    }

                    VStack(alignment: .leading, spacing: 8) {
                        Text("Model")
                            .font(.subheadline.bold())
                        Picker("Model", selection: $selectedModel) {
                            ForEach(ModelChoice.allCases) { choice in
                                Text(choice.displayName).tag(choice)
                            }
                        }
                        .pickerStyle(.menu)
                    }

                    VStack(alignment: .leading, spacing: 8) {
                        Text("OCR Pipeline")
                            .font(.subheadline.bold())
                        Picker("OCR Mode", selection: $selectedOCR) {
                            ForEach(OCRMode.allCases) { mode in
                                Text(mode.label).tag(mode)
                            }
                        }
                        .pickerStyle(.menu)
                    }

                    VStack(alignment: .leading, spacing: 12) {
                        Text("Image")
                            .font(.subheadline.bold())
                        PhotosPicker(
                            selection: $selectedItem,
                            matching: .images,
                            preferredItemEncoding: .automatic
                        ) {
                            Label("Choose a photo", systemImage: "photo.on.rectangle")
                        }
                        .buttonStyle(.borderedProminent)
                        .onChange(of: selectedItem) { newValue in
                            loadImage(from: newValue)
                        }

                        if let preview = imagePreview {
                            Image(uiImage: preview)
                                .resizable()
                                .scaledToFit()
                                .frame(maxHeight: 200)
                                .cornerRadius(10)
                                .overlay(
                                    RoundedRectangle(cornerRadius: 10)
                                        .stroke(Color.gray.opacity(0.2), lineWidth: 1)
                                )
                        } else {
                            Text("No image selected yet.")
                                .font(.footnote)
                                .foregroundColor(.secondary)
                        }
                    }

                    Button {
                        sendImage()
                    } label: {
                        HStack {
                            if isSending {
                                ProgressView()
                            }
                            Text(isSending ? "Sending..." : "Send to Harmony")
                        }
                        .frame(maxWidth: .infinity)
                    }
                    .disabled(imageData == nil || isSending)
                    .buttonStyle(.borderedProminent)

                    VStack(alignment: .leading, spacing: 8) {
                        Text("Status")
                            .font(.subheadline.bold())
                        Text(statusText)
                            .font(.footnote)
                            .foregroundColor(.secondary)
                    }

                    if let responseText {
                        VStack(alignment: .leading, spacing: 8) {
                            Text("Response")
                                .font(.subheadline.bold())
                            Text(responseText)
                                .font(.footnote.monospaced())
                                .frame(maxWidth: .infinity, alignment: .leading)
                                .padding(10)
                                .background(Color(.secondarySystemBackground))
                                .cornerRadius(8)
                        }
                    }

                    if let errorText {
                        VStack(alignment: .leading, spacing: 8) {
                            Text("Error")
                                .font(.subheadline.bold())
                                .foregroundColor(.red)
                            Text(errorText)
                                .font(.footnote)
                                .foregroundColor(.red)
                        }
                    }
                }
                .padding()
            }
            .navigationTitle("Harmony Client")
        }
    }

    private func loadImage(from item: PhotosPickerItem?) {
        guard let item else { return }
        Task {
            do {
                if let data = try await item.loadTransferable(type: Data.self),
                   let uiImage = UIImage(data: data) {
                    let jpegData = uiImage.jpegData(compressionQuality: 0.9) ?? data
                    await MainActor.run {
                        imagePreview = uiImage
                        imageData = jpegData
                        responseText = nil
                        errorText = nil
                        statusText = "Ready to upload."
                    }
                } else {
                    await MainActor.run {
                        errorText = "Could not read image data."
                        statusText = "Image required."
                    }
                }
            } catch {
                await MainActor.run {
                    errorText = error.localizedDescription
                    statusText = "Image load failed."
                }
            }
        }
    }

    private func sendImage() {
        guard let imageData else {
            errorText = "Pick an image first."
            statusText = "Image required."
            return
        }
        isSending = true
        statusText = "Uploading..."
        responseText = nil
        errorText = nil

        Task {
            do {
                let client = try HarmonyClient(baseURLString: serverURLString)
                let response = try await client.uploadImage(
                    data: imageData,
                    modelString: selectedModel.rawValue,
                    ocrMode: selectedOCR
                )
                let formatted = """
                OCR Text:
                \(response.ocrText)

                Event:
                \(response.event.prettyPrinted())
                """
                await MainActor.run {
                    responseText = formatted
                    statusText = "Success with \(selectedOCR.rawValue) via \(selectedModel.displayName)."
                }
            } catch {
                await MainActor.run {
                    errorText = error.localizedDescription
                    statusText = "Upload failed."
                }
            }
            await MainActor.run {
                isSending = false
            }
        }
    }

    private func checkHealth() {
        isCheckingHealth = true
        healthText = "Checking..."
        errorText = nil

        Task {
            do {
                let client = try HarmonyClient(baseURLString: serverURLString)
                let status = try await client.health()
                await MainActor.run {
                    healthText = "Server status: \(status)"
                }
            } catch {
                await MainActor.run {
                    healthText = "Health check failed."
                    errorText = error.localizedDescription
                }
            }
            await MainActor.run {
                isCheckingHealth = false
            }
        }
    }
}

#Preview {
    ContentView()
}
