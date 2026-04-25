"use client";
import { useEffect, useRef, useState } from "react";
import type { Profile } from "@/types/api";
import { SecondaryInputs } from "./SecondaryInputs";

export function AddressIntake({
  initialAddress = "Hauptstraße 1, 10827 Berlin",
  onSubmit,
  disabled,
}: {
  initialAddress?: string;
  onSubmit: (p: Profile) => void;
  disabled?: boolean;
}) {
  const [address, setAddress] = useState(initialAddress);
  const [step, setStep] = useState<1 | 2>(1);
  const [monthlyBillEur, setMonthlyBillEur] = useState(180);
  const [inhabitants, setInhabitants] = useState(2);
  const [heating, setHeating] = useState<Profile["heating"]>("gas");
  const [hasEv, setHasEv] = useState(false);
  const [evKmPerYear, setEvKmPerYear] = useState(12000);
  const [fileName, setFileName] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (step === 1) {
      inputRef.current?.focus();
      inputRef.current?.select();
    }
  }, [step]);

  const ready = address.trim().length > 4;

  function continueToStep2() {
    if (!ready) return;
    setStep(2);
  }

  function submit() {
    if (!ready || disabled) return;
    onSubmit({
      address,
      monthlyBillEur,
      inhabitants,
      heating,
      hasEv,
      ...(hasEv ? { evKmPerYear } : {}),
    });
  }

  return (
    <div className="flex h-screen w-screen flex-col">
      <header className="flex h-14 items-center px-6">
        <span className="text-[15px] font-semibold tracking-tight text-ink">
          Roofee
        </span>
      </header>

      {step === 1 ? (
        <main className="flex flex-1 items-center justify-center px-6">
          <div className="w-full max-w-[640px] -mt-12">
            <h1
              className="rise text-center text-[34px] md:text-[40px] font-medium leading-[1.15] tracking-tight text-ink"
              style={{ animationDelay: "20ms" }}
            >
              Let&rsquo;s design your solar system.
            </h1>
            <p
              className="rise mt-4 text-center text-[15px] text-dust"
              style={{ animationDelay: "100ms" }}
            >
              Start with the home&rsquo;s address.
            </p>

            <div
              className="rise mt-12"
              style={{ animationDelay: "180ms" }}
            >
              <input
                ref={inputRef}
                className="input-hero text-[26px] md:text-[30px]"
                value={address}
                onChange={(e) => setAddress(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") continueToStep2();
                }}
                placeholder="Street and city"
                spellCheck={false}
              />
            </div>

            <div
              className="rise mt-10 flex justify-center"
              style={{ animationDelay: "260ms" }}
            >
              <button
                type="button"
                disabled={!ready || disabled}
                onClick={continueToStep2}
                className="inline-flex items-center gap-2 rounded-full bg-ink px-8 py-3.5 text-[14px] font-medium text-paper transition hover:bg-signal disabled:cursor-not-allowed disabled:bg-ink/25"
              >
                Continue
                <span aria-hidden>→</span>
              </button>
            </div>

            <div
              className="rise mt-10 text-center"
              style={{ animationDelay: "340ms" }}
            >
              <label className="cursor-pointer text-[13px] text-dust underline-offset-4 hover:text-ink hover:underline">
                <input
                  type="file"
                  accept=".glb,.gltf,model/gltf-binary,model/gltf+json"
                  className="hidden"
                  onChange={(e) =>
                    setFileName(e.target.files?.[0]?.name ?? null)
                  }
                />
                {fileName ? `Selected: ${fileName}` : "or upload your own 3D model"}
              </label>
            </div>
          </div>
        </main>
      ) : (
        <main className="flex flex-1 items-start justify-center px-6 py-8">
          <div className="w-full max-w-[640px]">
            <button
              type="button"
              onClick={() => setStep(1)}
              className="rise text-[13px] text-dust transition hover:text-ink"
              style={{ animationDelay: "20ms" }}
            >
              ← {address}
            </button>

            <h1
              className="rise mt-6 text-[28px] font-medium leading-tight tracking-tight text-ink"
              style={{ animationDelay: "60ms" }}
            >
              A few details about the home.
            </h1>
            <p
              className="rise mt-2 text-[14px] text-dust"
              style={{ animationDelay: "120ms" }}
            >
              We use these to size the system. You can change everything later.
            </p>

            <div
              className="rise mt-10"
              style={{ animationDelay: "180ms" }}
            >
              <SecondaryInputs
                monthlyBillEur={monthlyBillEur}
                onMonthlyBillEur={setMonthlyBillEur}
                inhabitants={inhabitants}
                onInhabitants={setInhabitants}
                heating={heating}
                onHeating={setHeating}
                hasEv={hasEv}
                onHasEv={setHasEv}
                evKmPerYear={evKmPerYear}
                onEvKmPerYear={setEvKmPerYear}
              />
            </div>

            <div className="mt-10 flex items-center justify-end gap-4">
              <button
                type="button"
                onClick={() => setStep(1)}
                className="text-[13px] text-dust transition hover:text-ink"
              >
                Back
              </button>
              <button
                type="button"
                disabled={!ready || disabled}
                onClick={submit}
                className="inline-flex items-center gap-2 rounded-full bg-signal px-8 py-3.5 text-[14px] font-medium text-paper transition hover:bg-ink disabled:cursor-not-allowed disabled:bg-ink/25"
              >
                Design my system
                <span aria-hidden>→</span>
              </button>
            </div>
          </div>
        </main>
      )}
    </div>
  );
}
