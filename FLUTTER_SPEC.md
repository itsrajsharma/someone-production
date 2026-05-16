# Someone v1 — Flutter Mobile Specification

This document provides a comprehensive architectural and UI/UX blueprint for translating the "Someone v1" web application into a native Flutter application (iOS & Android).

---

## 1. Project Overview
- **App Name:** Someone
- **Purpose:** A pipeline-first, stateful AI companion with multiple personas (Aria & Oracle) capable of long-term semantic memory, routine extraction, and emotional fingerprinting.
- **Target Platforms:** Android and iOS
- **Backend:** FastAPI hosted on Render (`https://someone-rh2d.onrender.com`)
- **Auth System:** Supabase JWT

---

## 2. Tech Stack Recommendations
To ensure a robust, scalable, and highly performant mobile app, the following Flutter stack is required:

- **State Management:** **Riverpod**
  - *Reason:* Safest, most testable state management approach. Excellent for handling deep asynchronous pipelines (auth state, persona switching, and websocket/audio streams).
- **HTTP Client:** **Dio**
  - *Reason:* Allows global interceptors to effortlessly inject the `Authorization`, `X-Session-ID`, and `X-Local-Time` headers into every single request.
- **Secure Persistence:** **`flutter_secure_storage`**
  - *Reason:* Safely stores the Supabase JWT access token on-device.
- **Text-to-Speech (TTS):** **`just_audio`** (for playing base64 audio responses)
  - *Note:* The backend currently returns Base64 audio strings from Microsoft Edge TTS. The app will need to decode Base64 to a temporary file and play it via `just_audio`.
- **Speech-to-Text (Voice Input):** **`speech_to_text`**
  - *Reason:* For the Push-to-Talk voice overlay functionality.
- **Orb Animation:** **CustomPainter** integrated with `AnimationController`.
  - *Reason:* The AI Orb uses radial gradients, dynamic box shadows, and blurred inset overlays that react to state changes. A custom painter gives absolute programmatic control over the glow radius and color shifts when switching personas.
- **Navigation:** **GoRouter**
  - *Reason:* Provides strict declarative routing, making deep-linking and auth-guard redirection (e.g., kicking unauthenticated users to `/login`) seamless.

---

## 3. Full Folder Structure
Use a feature-first architecture to keep domains isolated.

```text
lib/
├── core/
│   ├── network/          # Dio client, Interceptors, API endpoints
│   ├── theme/            # Colors, Typography, AppTheme
│   ├── utils/            # Timezone formatters, JWT decoders
│   └── router/           # GoRouter configuration
├── features/
│   ├── auth/             
│   │   ├── presentation/ # LoginScreen, SignupScreen
│   │   ├── provider/     # Auth notifier (Riverpod)
│   │   └── data/         # secure_storage repository
│   ├── chat/             
│   │   ├── presentation/ # ChatScreen, VoiceOverlay, MessageBubble
│   │   ├── provider/     # Chat history state, Persona switcher state
│   │   └── data/         # Repository for /chat, /oracle, /intro endpoints
│   ├── health/           
│   │   ├── presentation/ # HealthUploadScreen
│   │   └── data/         # CSV file upload repository
│   └── dashboard/        
│       └── presentation/ # Main layout (Orb header + Tab view)
├── shared/
│   └── widgets/          # OrbWidget, GlassPanel, ActionButtons
└── main.dart             # ProviderScope setup & app initialization
```

---

## 4. Screen-by-Screen Specification

### A. Splash Screen
- **What it does:** Verifies if a valid JWT token exists in `flutter_secure_storage`. If valid, routes to Main Screen; if missing/expired, routes to Auth Screen.
- **UI:** Deep black background `#050505` with a subtle centered purple glow `#a78bfa`.

### B. Auth Screen (Login / Signup)
- **What it does:** Allows the user to authenticate via Supabase Auth.
- **UI Elements:**
  - **Background:** Deep black `#050505`.
  - **Inputs:** Email and Password text fields inside glassmorphism panels (opacity 0.6 black with blur).
  - **Action:** A primary button that changes theme based on the active mode.
  - **Toggle:** "Switch to Sign Up / Login" text button.
- **API Calls:** 
  - `POST /auth/login` (Expects `email`, `password`)
  - `POST /auth/signup` (Expects `email`, `password`)
- **Flow:** On success, store the `access_token` and `session_id` locally, then `context.go('/chat')`.

### C. Main Screen (Dashboard + Chat)
- **What it does:** The primary interface. Displays the interactive AI Orb at the top and the conversation timeline below it.
- **UI Elements:**
  - **Orb Container:** Top 40% of the screen. Dark background. Centered `OrbWidget`.
  - **Persona Toggle:** Minimalist buttons below the orb to switch between `Aria` and `Oracle`.
  - **Chat Panel:** Bottom 60%. A scrolling ListView of message bubbles.
  - **Input Bar:** Text field + Voice hold-to-talk button.
- **API Calls:**
  - `GET /intro/{persona}` (Fired when launching or switching personas)
  - `POST /chat` (For talking to Aria)
  - `POST /oracle` (For talking to Oracle)

### D. Push-to-Talk Voice Overlay
- **What it does:** A full-screen translucent overlay that appears when the user holds the mic button.
- **UI Elements:**
  - **Background:** `rgba(5,5,5,0.9)` with absolute heavy blur (`BackdropFilter`).
  - **Visualizer:** A pulsing ring reacting to mic levels.
  - **Transcript:** Live scrolling text of what the user is saying.
- **Flow:** On release, overlay closes and the transcript is submitted to the active persona's endpoint.

---

## 5. Orb Animation Spec (The `OrbWidget`)

The core personality identity is visually represented by the Orb. 
It requires a `CustomPainter` combining a solid circle, an inner radial gradient, and outer `BoxShadow` glows.

**States:**
1. **Idle Breathing:** The orb scales up and down slightly (`scale(1.0)` to `scale(1.05)`) over a 4-second cubic-bezier infinite loop.
2. **Thinking:** Rapid pulsing of the outer glow opacity.
3. **Persona Switch:** An explicit 300ms `scale(1.1)` bump, alongside a crossfade interpolation between colors.

**Color Mapping:**
- **Aria:** Base color `#b318bb` (Magenta/Purple). Box Shadow `rgba(198, 4, 198, 0.73)`.
- **Oracle:** Base color `#1e40af` (Deep Blue). Box Shadow `rgba(30, 64, 175, 0.5)`.

---

## 6. API Integration Layer

**Base URL:** `https://someone-rh2d.onrender.com`

### Global `Dio` Interceptor
Every authenticated request **MUST** include these three headers:
```dart
options.headers["Authorization"] = "Bearer $accessToken";
options.headers["X-Session-ID"] = "$sessionId"; // UUID generated on login
options.headers["X-Local-Time"] = "$localTimeString"; // e.g., "Sunday, 10:45 PM"
```

### Endpoints
1. **Chat (Aria)**
   - `POST /chat`
   - **Body:** `{ "message": "string" }`
   - **Response:** `{ "status": "success", "reply": "...", "audio": "base64..." }`
2. **Oracle**
   - `POST /oracle`
   - **Body:** `{ "message": "string" }`
   - **Response:** `{ "status": "success", "reply": "...", "audio": null }`
3. **Intro Sequence**
   - `GET /intro/{persona}`
   - **Response:** `{ "status": "...", "reply": "...", "audio": "..." }`
4. **Health Sync**
   - `POST /health`
   - **Body:** `MultipartFile` (CSV Upload)
   - **Response:** `{ "avg_sleep": 7.2, "avg_stress": 4.1 ... }`

---

## 7. Design Tokens

### Colors (Hex)
- **Backgrounds:**
  - Deep Black: `0xFF050505`
  - Charcoal Glass: `0x99121212` (Opacity 0.6)
- **Aria Persona:**
  - Glow (Lavender): `0xFFA78BFA`
  - Accent (Cyan): `0xFF22D3EE`
- **Oracle Persona:**
  - Base Shadow: `0xFF1E40AF`
  - Light Accent: `0xFF93C5FD`
- **Text:**
  - Primary Content: `0xFFE5E7EB` (Gray 200)

### Typography
- **Primary Font:** `Inter` (Google Fonts)
- **Persona Labels ("A R I A"):**
  - Font Size: 9px
  - Letter Spacing: `0.35em`
  - Text Transform: Uppercase
  - Opacity: 0.22
- **Body Text:**
  - Font Size: 14px (0.875rem)
  - Font Weight: 300 (Light)
  - Line Height: 1.8

### Glassmorphism Theme (Flutter)
To replicate the `.glass-panel` web CSS:
```dart
ClipRRect(
  borderRadius: BorderRadius.circular(16),
  child: BackdropFilter(
    filter: ImageFilter.blur(sigmaX: 12.0, sigmaY: 12.0),
    child: Container(color: const Color(0x99121212)),
  ),
)
```
