"use client";

// Firebase Auth phía trình duyệt (spec 06 §1). Ở local dùng emulator (NEXT_PUBLIC_FIREBASE_AUTH_EMULATOR_HOST).
import { type FirebaseApp, getApps, initializeApp } from "firebase/app";
import { type Auth, type User, connectAuthEmulator, getAuth, onIdTokenChanged } from "firebase/auth";
import { useEffect, useState } from "react";

let app: FirebaseApp | null = null;
let authInstance: Auth | null = null;

export function firebaseAuth(): Auth {
  if (authInstance) return authInstance;
  app =
    getApps()[0] ??
    initializeApp({
      apiKey: process.env.NEXT_PUBLIC_FIREBASE_API_KEY ?? "local-api-key",
      authDomain: process.env.NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN ?? "localhost",
      projectId: process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID ?? "dataxland-local",
    });
  authInstance = getAuth(app);
  authInstance.languageCode = "vi";
  const emu = process.env.NEXT_PUBLIC_FIREBASE_AUTH_EMULATOR_HOST;
  if (emu) connectAuthEmulator(authInstance, `http://${emu}`, { disableWarnings: true });
  return authInstance;
}

/** ID token hiện tại (tự làm mới khi sắp hết hạn); null khi chưa đăng nhập. */
export async function idToken(): Promise<string | null> {
  const user = firebaseAuth().currentUser;
  return user ? user.getIdToken() : null;
}

export type AuthState = { user: User | null; loading: boolean };

export function useAuthUser(): AuthState {
  const [state, setState] = useState<AuthState>({ user: null, loading: true });
  useEffect(() => onIdTokenChanged(firebaseAuth(), (user) => setState({ user, loading: false })), []);
  return state;
}
