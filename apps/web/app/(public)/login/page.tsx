"use client";

// Đăng nhập (spec 05 §3.1): email + mật khẩu có xác minh email, và Google.
import {
  GoogleAuthProvider,
  createUserWithEmailAndPassword,
  sendEmailVerification,
  sendPasswordResetEmail,
  signInWithEmailAndPassword,
  signInWithPopup,
  updateProfile,
} from "firebase/auth";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { firebaseAuth, useAuthUser } from "@/lib/auth/firebase";

const MESSAGES: Record<string, string> = {
  "auth/invalid-credential": "Email hoặc mật khẩu không đúng",
  "auth/wrong-password": "Email hoặc mật khẩu không đúng",
  "auth/user-not-found": "Email hoặc mật khẩu không đúng",
  "auth/email-already-in-use": "Email đã có tài khoản; hãy đăng nhập",
  "auth/weak-password": "Mật khẩu cần ít nhất 8 ký tự",
  "auth/too-many-requests": "Thử quá nhiều lần, vui lòng đợi vài phút",
  "auth/popup-closed-by-user": "Đã đóng cửa sổ đăng nhập Google",
};

function message(e: unknown): string {
  const code = (e as { code?: string })?.code ?? "";
  return MESSAGES[code] ?? "Không đăng nhập được, thử lại sau";
}

function safeNext(next: string | null): string {
  return next && next.startsWith("/") && !next.startsWith("//") ? next : "/app";
}

function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const next = safeNext(params.get("next"));
  const { user, loading } = useAuthUser();
  const [mode, setMode] = useState<"login" | "signup" | "reset">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);

  useEffect(() => {
    if (
      !loading &&
      user &&
      (user.emailVerified || !user.providerData.some((p) => p.providerId === "password"))
    ) {
      router.replace(next);
    }
  }, [loading, user, router, next]);

  const run = async (fn: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    setInfo(null);
    try {
      await fn();
    } catch (e) {
      setError(message(e));
    } finally {
      setBusy(false);
    }
  };

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const auth = firebaseAuth();
    if (mode === "reset") {
      void run(async () => {
        await sendPasswordResetEmail(auth, email);
        setInfo("Đã gửi email đặt lại mật khẩu nếu email có tài khoản.");
      });
    } else if (mode === "signup") {
      void run(async () => {
        if (password.length < 8) throw { code: "auth/weak-password" };
        const cred = await createUserWithEmailAndPassword(auth, email, password);
        if (name) await updateProfile(cred.user, { displayName: name });
        await sendEmailVerification(cred.user, { url: `${window.location.origin}${next}` });
        setInfo(`Đã gửi email xác minh tới ${email}. Mở thư, bấm link rồi quay lại đăng nhập.`);
      });
    } else {
      void run(async () => {
        const cred = await signInWithEmailAndPassword(auth, email, password);
        if (!cred.user.emailVerified) {
          await sendEmailVerification(cred.user);
          setInfo("Email chưa xác minh. Đã gửi lại thư xác minh.");
          return;
        }
        router.replace(next);
      });
    }
  };

  return (
    <main className="mx-auto flex min-h-screen max-w-sm flex-col justify-center px-6">
      <h1 className="mb-1 text-2xl font-semibold">DataxLand</h1>
      <p className="mb-6 text-sm text-slate-500">
        {mode === "signup"
          ? "Tạo tài khoản"
          : mode === "reset"
            ? "Đặt lại mật khẩu"
            : "Đăng nhập vào cổng khách hàng"}
      </p>
      <button
        type="button"
        className="btn-secondary mb-4 w-full"
        disabled={busy}
        onClick={() =>
          run(async () => {
            await signInWithPopup(firebaseAuth(), new GoogleAuthProvider());
            router.replace(next);
          })
        }
      >
        Tiếp tục với Google
      </button>
      <div className="mb-4 text-center text-xs text-slate-400">hoặc dùng email</div>
      <form onSubmit={submit} className="space-y-3">
        {mode === "signup" && (
          <label className="block">
            <span className="label">Họ tên</span>
            <input
              className="input"
              value={name}
              onChange={(e) => setName(e.target.value)}
              autoComplete="name"
            />
          </label>
        )}
        <label className="block">
          <span className="label">Email</span>
          <input
            className="input"
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            autoComplete="email"
          />
        </label>
        {mode !== "reset" && (
          <label className="block">
            <span className="label">Mật khẩu</span>
            <input
              className="input"
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete={mode === "signup" ? "new-password" : "current-password"}
            />
          </label>
        )}
        {error && (
          <p className="text-sm text-red-700" role="alert">
            {error}
          </p>
        )}
        {info && <p className="text-sm text-green-700">{info}</p>}
        <button type="submit" className="btn-primary w-full" disabled={busy}>
          {mode === "signup" ? "Tạo tài khoản" : mode === "reset" ? "Gửi email đặt lại" : "Đăng nhập"}
        </button>
      </form>
      <div className="mt-4 flex justify-between text-sm">
        {mode === "login" ? (
          <>
            <button type="button" className="text-brand-600" onClick={() => setMode("signup")}>
              Tạo tài khoản
            </button>
            <button type="button" className="text-slate-500" onClick={() => setMode("reset")}>
              Quên mật khẩu?
            </button>
          </>
        ) : (
          <button type="button" className="text-brand-600" onClick={() => setMode("login")}>
            ← Quay lại đăng nhập
          </button>
        )}
      </div>
    </main>
  );
}

export default function LoginPage() {
  return (
    <Suspense>
      <LoginForm />
    </Suspense>
  );
}
