"use client";

import { Component, Suspense, useCallback, useEffect, useRef, useState } from "react";
import type { ReactNode, RefObject } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import { OrbitControls } from "@react-three/drei";
import * as THREE from "three";
import { Box } from "lucide-react";

export type AvatarEmotion =
  | "calm"
  | "neutral"
  | "rushed"
  | "frustrated"
  | "upset"
  | "warm"
  | "worried";

export interface AvatarViewerProps {
  vrmUrl: string;
  audioRef?: RefObject<HTMLAudioElement | null>;
  emotion?: AvatarEmotion;
  className?: string;
}

type LoadStatus = "idle" | "loading" | "ready" | "error";

// Canonical emotion keys -> target weights. Resolved to real VRM preset
// names (v0/v1 aliases) at apply time so unknown presets are skipped.
const EMOTION_TARGETS: Record<AvatarEmotion, Record<string, number>> = {
  calm: { neutral: 0.2, relaxed: 0.35 },
  neutral: { neutral: 0.12 },
  rushed: { surprised: 0.3, neutral: 0.1 },
  frustrated: { angry: 0.75 },
  upset: { sad: 0.75 },
  warm: { happy: 0.8 },
  worried: { surprised: 0.45, sad: 0.35 },
};

const EMOTION_ALIASES: Record<string, string[]> = {
  angry: ["angry"],
  sad: ["sad", "sorrow"],
  happy: ["happy", "fun", "joy"],
  surprised: ["surprised"],
  neutral: ["neutral"],
  relaxed: ["relaxed"],
};

const VISEME_ALIASES: Record<string, string[]> = {
  aa: ["aa", "a"],
  ih: ["ih", "i"],
  ou: ["ou", "u"],
  ee: ["ee", "e"],
  oh: ["oh", "o"],
};

const BLINK_NAMES = ["blink"];
const BLINK_SIDE_NAMES = ["blinkLeft", "blinkRight"];

function setExpression(vrm: any, names: string[], value: number): void {
  try {
    const em = vrm?.expressionManager;
    if (!em || typeof em.setValue !== "function") return;
    const map: Record<string, any> = em.expressionMap || {};
    for (const n of names) {
      if (map[n]) {
        try {
          em.setValue(n, value);
        } catch {
          /* ignore per-expression failures */
        }
        return;
      }
    }
    // Fall back to trying the first name (some managers accept unknowns).
    try {
      em.setValue(names[0], value);
    } catch {
      /* noop */
    }
  } catch {
    /* never crash on expression writes */
  }
}

function disposeObject(root: any): void {
  try {
    root?.traverse?.((o: any) => {
      try {
        if (o.geometry && typeof o.geometry.dispose === "function") o.geometry.dispose();
        const mats = Array.isArray(o.material) ? o.material : o.material ? [o.material] : [];
        for (const m of mats) {
          try {
            for (const v of Object.values(m || {})) {
              try {
                if (v && (v as any).isTexture && typeof (v as any).dispose === "function")
                  (v as any).dispose();
              } catch {
                /* noop */
              }
            }
            if (typeof m.dispose === "function") m.dispose();
          } catch {
            /* noop */
          }
        }
      } catch {
        /* noop */
      }
    });
  } catch {
    /* noop */
  }
}

interface ModelProps {
  url: string;
  emotion: AvatarEmotion;
  audioRef?: RefObject<HTMLAudioElement | null>;
  onStatus: (s: LoadStatus, msg?: string) => void;
}

function AvatarModel({ url, emotion, audioRef, onStatus }: ModelProps) {
  const [vrm, setVrm] = useState<any>(null);
  const [plain, setPlain] = useState<any>(null);
  const vrmRef = useRef<any>(null);
  const headRef = useRef<any>(null);
  const baseRot = useRef(new THREE.Euler());
  const sceneRef = useRef<any>(null);
  const blinkRef = useRef({ next: 2.5, until: -1 });
  const emoTarget = useRef<Record<string, number>>({});
  const emoCurrent = useRef<Record<string, number>>({});
  const mouthCurrent = useRef<Record<string, number>>({ aa: 0, ih: 0, ou: 0, ee: 0, oh: 0 });
  const engineRef = useRef<any>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const analyserData = useRef<Uint8Array | null>(null);
  const rmsRef = useRef(0);
  const statusCb = useRef(onStatus);
  statusCb.current = onStatus;

  // ---- emotion targets follow the prop ----
  useEffect(() => {
    try {
      emoTarget.current = { ...(EMOTION_TARGETS[emotion] || EMOTION_TARGETS.neutral) };
    } catch {
      emoTarget.current = {};
    }
  }, [emotion]);

  // ---- load VRM (or plain GLB fallback) ----
  useEffect(() => {
    let cancelled = false;
    if (!url || !url.trim()) {
      try {
        statusCb.current("idle");
      } catch {
        /* noop */
      }
      return;
    }
    try {
      statusCb.current("loading");
    } catch {
      /* noop */
    }
    setVrm(null);
    setPlain(null);
    vrmRef.current = null;
    headRef.current = null;

    (async () => {
      let nextScene: any = null;
      let nextVrm: any = null;
      let nextPlain: any = null;
      try {
        const loaderMod: any = await import("three/addons/loaders/GLTFLoader.js");
        const vrmMod: any = await import("@pixiv/three-vrm");
        const GLTFLoader = loaderMod.GLTFLoader || loaderMod.default;
        if (!GLTFLoader) throw new Error("GLTFLoader unavailable");
        const loader = new GLTFLoader();
        try {
          if (vrmMod.VRMLoaderPlugin) loader.register((parser: any) => new vrmMod.VRMLoaderPlugin(parser));
        } catch {
          /* plugin registration is best-effort */
        }
        loader.setCrossOrigin("anonymous");
        const gltf: any = await loader.loadAsync(url.trim());
        if (cancelled) return;
        const loadedVrm = gltf?.userData?.vrm ?? null;
        if (loadedVrm) {
          nextVrm = loadedVrm;
          nextScene = loadedVrm.scene;
          try {
            const box = new THREE.Box3().setFromObject(nextScene);
            const c = box.getCenter(new THREE.Vector3());
            if (Number.isFinite(c.x)) nextScene.position.x -= c.x;
            if (Number.isFinite(c.z)) nextScene.position.z -= c.z;
          } catch {
            /* framing is best-effort */
          }
          try {
            const h =
              loadedVrm.humanoid?.getNormalizedBoneNode?.("head") ||
              loadedVrm.humanoid?.getRawBoneNode?.("head") ||
              null;
            headRef.current = h;
            if (h) baseRot.current.copy(h.rotation);
          } catch {
            headRef.current = null;
          }
        } else if (gltf?.scene) {
          // Plain GLB (e.g. Ready Player Me without VRM data): render it anyway.
          nextPlain = gltf.scene;
          nextScene = gltf.scene;
          try {
            const box = new THREE.Box3().setFromObject(nextScene);
            const c = box.getCenter(new THREE.Vector3());
            if (Number.isFinite(c.x)) nextScene.position.x -= c.x;
            if (Number.isFinite(c.z)) nextScene.position.z -= c.z;
          } catch {
            /* noop */
          }
        } else {
          throw new Error("File did not contain a 3D scene");
        }
        if (cancelled) {
          disposeObject(nextScene);
          return;
        }
        sceneRef.current = nextScene;
        vrmRef.current = nextVrm;
        if (nextVrm) setVrm(nextVrm);
        else setPlain(nextPlain);
        try {
          statusCb.current("ready");
        } catch {
          /* noop */
        }
      } catch (e: any) {
        try {
          disposeObject(nextScene);
        } catch {
          /* noop */
        }
        if (cancelled) return;
        let msg = "Could not load this avatar URL.";
        try {
          const raw = String(e?.message || e || "");
          if (raw) msg = `Could not load avatar: ${raw.slice(0, 160)}`;
        } catch {
          /* keep default */
        }
        try {
          statusCb.current("error", msg);
        } catch {
          /* noop */
        }
      }
    })();

    return () => {
      cancelled = true;
      try {
        engineRef.current?.dispose?.();
      } catch {
        /* noop */
      }
      engineRef.current = null;
      analyserRef.current = null;
      analyserData.current = null;
      try {
        disposeObject(sceneRef.current);
      } catch {
        /* noop */
      }
      sceneRef.current = null;
      vrmRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [url]);

  // ---- lip-sync wiring: viseme engine (three-vrm-lip-sync) with amplitude fallback ----
  useEffect(() => {
    if (!vrm && !plain) return;
    const el = audioRef?.current;
    if (!el || typeof window === "undefined") return;
    let cancelled = false;
    let onPlay: (() => void) | null = null;
    let onPlaying: (() => void) | null = null;

    (async () => {
      try {
        const AC =
          (window as any).AudioContext || (window as any).webkitAudioContext;
        if (!AC) return;
        // Reuse the context already bound to this element if there is one:
        // createMediaElementSource may only be called once per element.
        const slotKey = "__vf_media_graph__";
        const existing: any = (el as any)[slotKey];
        let ctx: AudioContext;
        let srcNode: any = null;
        if (existing && existing.ctx && existing.ctx.state !== "closed") {
          ctx = existing.ctx;
          srcNode = existing.node;
        } else {
          ctx = new AC();
          try {
            await ctx.resume().catch(() => {});
          } catch {
            /* resume is best-effort */
          }
          try {
            srcNode = ctx.createMediaElementSource(el);
            (el as any)[slotKey] = { ctx, node: srcNode };
          } catch {
            // Element already bound to a different (now lost) context.
            srcNode = (el as any)[slotKey]?.node ?? null;
            if ((el as any)[slotKey]?.ctx) ctx = (el as any)[slotKey].ctx;
          }
        }
        if (cancelled) return;
        const resume = () => {
          try {
            const c: AudioContext | undefined = (el as any)[slotKey]?.ctx || ctx;
            if (c && c.state === "suspended") c.resume().catch(() => {});
          } catch {
            /* noop */
          }
        };
        onPlay = resume;
        onPlaying = resume;
        try {
          el.addEventListener("play", resume);
          el.addEventListener("playing", resume);
        } catch {
          /* noop */
        }
        // Path A (preferred): real viseme analysis via three-vrm-lip-sync.
        try {
          const mod: any = await import("three-vrm-lip-sync");
          if (cancelled) return;
          if (!mod?.WLipSyncEngine) throw new Error("lip-sync engine missing");
          const engine = await mod.WLipSyncEngine.create(ctx);
          if (cancelled) {
            try {
              engine.dispose();
            } catch {
              /* noop */
            }
            return;
          }
          try {
            if (srcNode) srcNode.connect(engine.input);
          } catch {
            /* graph wiring is best-effort */
          }
          engineRef.current = engine;
          try {
            (el as any).dataset.vfLip = "viseme";
          } catch {
            /* noop */
          }
        } catch {
          // Path B (fallback): amplitude-based jaw via AnalyserNode.
          try {
            if (cancelled) return;
            if (srcNode && ctx) {
              const an = ctx.createAnalyser();
              an.fftSize = 1024;
              an.smoothingTimeConstant = 0.55;
              try {
                srcNode.connect(an);
              } catch {
                /* noop */
              }
              analyserRef.current = an;
              analyserData.current = new Uint8Array(an.fftSize);
            }
            try {
              (el as any).dataset.vfLip = "amplitude";
            } catch {
              /* noop */
            }
          } catch {
            /* idle animation only */
          }
        }
      } catch {
        /* lip-sync is enhancement-only; idle animation continues */
      }
    })();

    return () => {
      cancelled = true;
      try {
        if (el && onPlay) el.removeEventListener("play", onPlay);
      } catch {
        /* noop */
      }
      try {
        if (el && onPlaying) el.removeEventListener("playing", onPlaying);
      } catch {
        /* noop */
      }
      try {
        engineRef.current?.dispose?.();
      } catch {
        /* noop */
      }
      engineRef.current = null;
      analyserRef.current = null;
      analyserData.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [vrm, plain]);

  // ---- per-frame: idle bob + blink + emotion + lip-sync, then vrm.update ----
  useFrame((state, rawDelta) => {
    try {
      const dt = Math.min(Math.max(rawDelta || 0.016, 0.001), 0.05);
      const t = state.clock?.elapsedTime ?? 0;
      const vrm = vrmRef.current;

      // Gentle head bob (or whole-model sway when no head bone / plain GLB).
      try {
        const head = headRef.current;
        if (head) {
          head.rotation.y = baseRot.current.y + Math.sin(t * 0.6) * 0.08;
          head.rotation.x = baseRot.current.x + Math.sin(t * 0.9) * 0.045;
          head.rotation.z = baseRot.current.z + Math.sin(t * 0.4) * 0.02;
        } else if (vrm?.scene) {
          vrm.scene.rotation.y = Math.sin(t * 0.4) * 0.03;
        } else if (plain) {
          plain.rotation.y = Math.sin(t * 0.4) * 0.03;
        }
      } catch {
        /* noop */
      }

      if (vrm) {
        // Periodic blink.
        try {
          const b = blinkRef.current;
          if (t > b.next) {
            b.until = t + 0.12;
            b.next = t + 2.2 + Math.random() * 3.2;
          }
          const w = t < b.until ? 1 : 0;
          setExpression(vrm, BLINK_NAMES, w);
          for (const n of BLINK_SIDE_NAMES) setExpression(vrm, [n], w);
        } catch {
          /* noop */
        }

        // Emotion: ease current weights toward targets.
        try {
          const tgt = emoTarget.current || {};
          const cur = emoCurrent.current;
          const keys = new Set([...Object.keys(EMOTION_ALIASES), ...Object.keys(cur)]);
          for (const k of keys) {
            const goal = Number(tgt[k] ?? 0);
            const have = Number(cur[k] ?? 0);
            const next = have + (goal - have) * Math.min(1, dt * 6);
            cur[k] = next;
            if (Math.abs(next) > 0.003 || Math.abs(goal) > 0) {
              setExpression(vrm, EMOTION_ALIASES[k] || [k], next);
            }
          }
        } catch {
          /* noop */
        }

        // Mouth: viseme engine first, amplitude jaw fallback.
        try {
          const targets: Record<string, number> = { aa: 0, ih: 0, ou: 0, ee: 0, oh: 0 };
          const eng = engineRef.current;
          let speaking = false;
          if (eng && eng.weights) {
            try {
              const w = eng.weights;
              const vol = Number(eng.volume ?? 0);
              if (vol > 0.03) {
                speaking = true;
                targets.aa = Math.min(1, Math.max(0, Number(w.aa ?? 0)));
                targets.ih = Math.min(1, Math.max(0, Number(w.ih ?? 0)));
                targets.ou = Math.min(1, Math.max(0, Number(w.ou ?? 0)));
                targets.ee = Math.min(1, Math.max(0, Number(w.ee ?? 0)));
                targets.oh = Math.min(1, Math.max(0, Number(w.oh ?? 0)));
              }
            } catch {
              /* fall through to closed mouth */
            }
          }
          if (!speaking && analyserRef.current && analyserData.current) {
            try {
              const an = analyserRef.current;
              const buf = analyserData.current;
              an.getByteTimeDomainData(buf as Uint8Array<ArrayBuffer>);
              let sum = 0;
              for (let i = 0; i < buf.length; i += 2) {
                const v = (buf[i] - 128) / 128;
                sum += v * v;
              }
              const rms = Math.sqrt(sum / (buf.length / 2));
              const sm = rmsRef.current + (rms - rmsRef.current) * Math.min(1, dt * 12);
              rmsRef.current = sm;
              const jaw = Math.min(1, Math.max(0, (sm - 0.015) * 5));
              if (jaw > 0.01) {
                speaking = true;
                targets.aa = jaw;
                targets.oh = jaw * 0.7;
                targets.ou = jaw * 0.4;
                targets.ee = jaw * 0.3;
                targets.ih = jaw * 0.3;
              }
            } catch {
              /* noop */
            }
          }
          const cur = mouthCurrent.current;
          const speed = speaking ? 18 : 8;
          for (const k of Object.keys(targets)) {
            const next = cur[k] + (targets[k] - cur[k]) * Math.min(1, dt * speed);
            cur[k] = next;
            if (next > 0.004) setExpression(vrm, VISEME_ALIASES[k] || [k], next);
            else if (cur[k] !== 0) {
              setExpression(vrm, VISEME_ALIASES[k] || [k], 0);
              cur[k] = 0;
            }
          }
        } catch {
          /* noop */
        }

        try {
          vrm.update(dt);
        } catch {
          /* noop */
        }
      }
    } catch {
      /* a frame must never crash the viewer */
    }
  });

  return (
    <>
      {vrm ? <primitive object={vrm.scene} /> : null}
      {!vrm && plain ? <primitive object={plain} /> : null}
    </>
  );
}

class CanvasErrorBoundary extends Component<{ children: ReactNode; onFail: () => void }, { failed: boolean }> {
  constructor(props: { children: ReactNode; onFail: () => void }) {
    super(props);
    this.state = { failed: false };
  }
  static getDerivedStateFromError(): { failed: boolean } {
    return { failed: true };
  }
  componentDidCatch(): void {
    try {
      this.props.onFail();
    } catch {
      /* noop */
    }
  }
  render(): ReactNode {
    if (this.state.failed) return null;
    return this.props.children;
  }
}

export default function AvatarViewer({ vrmUrl, audioRef, emotion = "neutral", className }: AvatarViewerProps) {
  const [mounted, setMounted] = useState(false);
  const [status, setStatus] = useState<LoadStatus>("idle");
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [webglFail, setWebglFail] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  // WebGL context loss -> friendly fallback instead of a frozen canvas.
  useEffect(() => {
    if (!mounted || typeof window === "undefined") return;
    const onLost = () => setWebglFail(true);
    try {
      window.addEventListener("webglcontextlost", onLost as EventListener);
    } catch {
      /* noop */
    }
    return () => {
      try {
        window.removeEventListener("webglcontextlost", onLost as EventListener);
      } catch {
        /* noop */
      }
    };
  }, [mounted]);

  const handleStatus = useCallback((s: LoadStatus, msg?: string) => {
    try {
      setStatus(s);
      setErrorMsg(s === "error" ? msg || "Could not load this avatar URL." : null);
    } catch {
      /* noop */
    }
  }, []);

  const handleCanvasFail = useCallback(() => {
    try {
      setWebglFail(true);
    } catch {
      /* noop */
    }
  }, []);

  const trimmed = (vrmUrl || "").trim();

  return (
    <div
      className={className || "relative h-[420px] w-full overflow-hidden rounded-2xl border border-white/10 bg-zinc-900/60"}
      style={{ background: "transparent" }}
    >
      {!mounted || webglFail ? (
        <div className="flex h-full w-full flex-col items-center justify-center gap-2 bg-zinc-900/80 p-6 text-center">
          <Box className="h-8 w-8 text-zinc-600" />
          <p className="text-sm font-medium text-zinc-300">
            {webglFail ? "3D preview unavailable" : "Preparing 3D preview…"}
          </p>
          <p className="max-w-[26ch] text-xs text-zinc-500">
            {webglFail
              ? "Your browser or device blocked WebGL, so the avatar cannot be rendered here. Voice chat still works."
              : "Loading…"}
          </p>
        </div>
      ) : !trimmed ? (
        <div className="flex h-full w-full flex-col items-center justify-center gap-2 bg-zinc-900/60 p-6 text-center">
          <Box className="h-8 w-8 text-zinc-600" />
          <p className="text-sm font-medium text-zinc-300">No avatar loaded</p>
          <p className="max-w-[30ch] text-xs text-zinc-500">
            Build one in step 1 or paste a .glb / .vrm URL, then press Load.
          </p>
        </div>
      ) : (
        <CanvasErrorBoundary onFail={handleCanvasFail}>
          <Canvas
            dpr={[1, 1.75]}
            camera={{ position: [0, 1.4, 2.2], fov: 32 }}
            gl={{ alpha: true, antialias: true, powerPreference: "high-performance" }}
            style={{ background: "transparent" }}
            onCreated={(state: any) => {
              try {
                state?.gl?.setClearColor?.(0x000000, 0);
              } catch {
                /* noop */
              }
              try {
                const el = state?.gl?.domElement;
                if (el) {
                  el.addEventListener("webglcontextlost", (e: Event) => {
                    try {
                      e.preventDefault();
                    } catch {
                      /* noop */
                    }
                    handleCanvasFail();
                  });
                }
              } catch {
                /* noop */
              }
            }}
          >
            {/* Soft key + rim lights for head-and-shoulders framing */}
            <ambientLight intensity={0.75} />
            <directionalLight position={[2, 3, 2.5]} intensity={1.25} />
            <directionalLight position={[-2.5, 2, -2]} intensity={0.65} color="#ffb37a" />
            <hemisphereLight args={["#e8e8f0", "#1a1a22", 0.35]} />
            <Suspense fallback={null}>
              <AvatarModel url={trimmed} emotion={emotion} audioRef={audioRef} onStatus={handleStatus} />
            </Suspense>
            <OrbitControls
              target={[0, 1.35, 0]}
              enablePan={false}
              enableDamping
              minDistance={1}
              maxDistance={4}
              maxPolarAngle={1.7}
              minPolarAngle={0.5}
            />
          </Canvas>
        </CanvasErrorBoundary>
      )}

      {/* Loading overlay */}
      {mounted && !webglFail && !!trimmed && status === "loading" ? (
        <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center gap-3 bg-zinc-950/40">
          <span className="h-8 w-8 animate-spin rounded-full border-2 border-zinc-600 border-t-orange-400" />
          <p className="text-xs text-zinc-400">Loading avatar…</p>
        </div>
      ) : null}

      {/* Error card: never crash on a bad URL */}
      {mounted && !webglFail && !!trimmed && status === "error" ? (
        <div className="absolute inset-x-3 bottom-3 rounded-xl border border-red-400/40 bg-red-950/85 p-3 backdrop-blur">
          <p className="text-xs font-semibold text-red-200">Avatar failed to load</p>
          <p className="mt-1 break-words text-xs text-red-300/90">{errorMsg || "Could not load this avatar URL."}</p>
        </div>
      ) : null}
    </div>
  );
}
