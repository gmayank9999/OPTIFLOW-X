"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { api, ApiError, GuardrailCheck, Health, ProgramDetail, ProgramRow, RunDetail, RunEvent, streamUrl, useApi } from "@/lib/api";
import { cx, CATEGORY_LABEL } from "@/lib/format";
import {
  deriveOutcome, detectLanguage, GOALS, GoalKey, Language, MAX_TEST_INPUTS, SAMPLES, validateCode, validateFile, validateTestInput,
} from "@/lib/workspace";
import { Segmented } from "@/components/ui";
import { CodeEditor } from "@/components/workspace/CodeEditor";
import { ProgressView } from "@/components/workspace/Progress";
import { ResultsView } from "@/components/workspace/Results";
import { Accordion, BigButton, Notice, RadioCard, Stepper } from "@/components/workspace/parts";

type Source = "sample" | "paste" | "upload";
type Method = "quick" | "smart";
type Effort = 1 | 3 | 5;

const FINISHED = ["done", "failed", "cancelled"];

export default function WorkspacePage() {
  const { data: programs } = useApi<ProgramRow[]>("/programs");
  const { data: health } = useApi<Health>("/health");

  const [step, setStep] = useState(1);

  // Step 1: the code
  const [source, setSource] = useState<Source>("sample");
  const [sampleId, setSampleId] = useState("matmul_naive");
  const [sampleCode, setSampleCode] = useState("");
  const [sampleLang, setSampleLang] = useState<Language>("c");
  const [code, setCode] = useState("");
  const [fileName, setFileName] = useState("");
  const [language, setLanguage] = useState<Language>("c");
  const [langTouched, setLangTouched] = useState(false);
  const [testInputs, setTestInputs] = useState<string[]>([]);
  const [codeError, setCodeError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  // Step 2: the goal
  const [goal, setGoal] = useState<GoalKey>("speed");
  const [customGoal, setCustomGoal] = useState("");
  const [guard, setGuard] = useState<GuardrailCheck | null>(null);

  // Step 3: how
  const [method, setMethod] = useState<Method>("quick");
  const [effort, setEffort] = useState<Effort>(3);
  const [strict, setStrict] = useState(true);

  // Steps 4-5: the run
  const [runId, setRunId] = useState<string | null>(null);
  const [events, setEvents] = useState<RunEvent[]>([]);
  const [runStatus, setRunStatus] = useState("queued");
  const [queuePos, setQueuePos] = useState(0);
  const [startedAt, setStartedAt] = useState(0);
  const [submitting, setSubmitting] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [result, setResult] = useState<RunDetail | null>(null);
  const [resultFile, setResultFile] = useState("main.c");
  const [resultLang, setResultLang] = useState<Language>("c");

  const running = step === 4;
  const isSample = source === "sample";
  const activeCode = isSample ? sampleCode : code;
  const activeLang = isSample ? sampleLang : language;
  const keyAvailable = !!health && Object.values(health.keys).some(Boolean);
  const dockerDown = !!health && !health.docker;
  const instructions = goal === "custom" ? customGoal.trim() : GOALS.find((g) => g.key === goal)!.instructions;

  // Load the chosen sample program's source.
  useEffect(() => {
    if (!isSample) return;
    let cancelled = false;
    api<ProgramDetail>(`/programs/${sampleId}`)
      .then((d) => {
        if (cancelled) return;
        setSampleCode(d.source);
        setSampleLang(d.meta.language === "c" ? "c" : "cpp");
      })
      .catch((e) => !cancelled && setCodeError(`Couldn't load that sample: ${e.message}`));
    return () => { cancelled = true; };
  }, [sampleId, isSample]);

  // Screen free-text goals before submitting, so the reason is visible.
  useEffect(() => {
    if (goal !== "custom" || !customGoal.trim()) { setGuard(null); return; }
    const t = setTimeout(() => {
      api<GuardrailCheck>("/guardrails/check", { method: "POST", body: JSON.stringify({ text: customGoal }) }).then(setGuard).catch(() => setGuard(null));
    }, 350);
    return () => clearTimeout(t);
  }, [goal, customGoal]);

  // Follow the run: live events over a WebSocket, with polling as the safety
  // net (and the way a missed final event is noticed).
  useEffect(() => {
    if (!runId) return;
    let done = false;
    const finish = async (known?: RunDetail) => {
      if (done) return;
      done = true;
      try {
        setResult(known ?? (await api<RunDetail>(`/runs/${runId}`)));
      } catch (e) {
        setSubmitError(`Couldn't load the result: ${(e as Error).message}`);
      }
      setCancelling(false);
      setStep(5);
    };
    let ws: WebSocket | null = null;
    try {
      ws = new WebSocket(streamUrl(runId));
      ws.onmessage = (m) => {
        try {
          const ev = JSON.parse(m.data) as RunEvent;
          setEvents((prev) => [...prev, ev]);
          if (ev.type === "run_start") setRunStatus("running");
          if (ev.type === "run_end") finish();
        } catch { /* ignore malformed frame */ }
      };
    } catch { /* polling below still works */ }
    const poll = setInterval(async () => {
      try {
        const d = await api<RunDetail>(`/runs/${runId}`);
        setRunStatus(d.status);
        if (FINISHED.includes(d.status)) finish(d);
        else if (d.events?.length) setEvents((prev) => (d.events.length > prev.length ? d.events : prev));
      } catch { /* transient; try again */ }
    }, 2500);
    return () => { done = true; clearInterval(poll); ws?.close(); };
  }, [runId]);

  const outcome = useMemo(() => (result ? deriveOutcome(result) : null), [result]);

  function pickFile(file: File) {
    const problem = validateFile(file);
    if (problem) { setCodeError(problem); return; }
    file.text().then((text) => {
      setCode(text);
      setFileName(file.name);
      setSource("upload");
      if (!langTouched) setLanguage(detectLanguage(text, file.name));
      setCodeError(validateCode(text));
    }).catch(() => setCodeError(`Couldn't read "${file.name}".`));
  }

  function editCode(text: string) {
    setCode(text);
    if (codeError) setCodeError(null);
    if (!langTouched) setLanguage(detectLanguage(text, fileName));
  }

  function goFromCode() {
    const problem = isSample ? (sampleCode ? null : "The sample is still loading.") : validateCode(code)
      ?? testInputs.map((t, i) => validateTestInput(t, i)).find(Boolean) ?? null;
    setCodeError(problem);
    if (!problem) setStep(2);
  }

  const goalProblem = goal === "custom" && (!customGoal.trim() ? "Describe what you'd like improved, or pick one of the options above." : guard && !guard.ok ? "That description was rejected by the safety filter. Please reword it." : null);

  async function optimize() {
    setSubmitting(true);
    setSubmitError(null);
    const variant = method === "smart" ? "full" : isSample ? "rule_only" : "flags_only";
    const common = {
      variant, instructions, max_attempts: effort,
      persona: strict ? "cautious_reviewer" : "default",
    };
    const body = isSample
      ? { program_id: sampleId, ...common }
      : { source: code, language, test_inputs: testInputs.filter((t) => t.trim()), ...common };
    try {
      const res = await api<{ run_id: string; position: number }>("/runs", { method: "POST", body: JSON.stringify(body) });
      setEvents([]);
      setResult(null);
      setRunStatus("queued");
      setQueuePos(res.position ?? 0);
      setStartedAt(Date.now());
      setResultFile(isSample ? (sampleLang === "c" ? "main.c" : "main.cpp") : fileName || (language === "c" ? "main.c" : "main.cpp"));
      setResultLang(activeLang);
      setRunId(res.run_id);
      setStep(4);
    } catch (e) {
      const err = e as ApiError;
      setSubmitError(err.message || "We couldn't start the optimization.");
    } finally {
      setSubmitting(false);
    }
  }

  async function cancel() {
    if (!runId) return;
    setCancelling(true);
    try {
      await api(`/runs/${runId}/cancel`, { method: "POST" });
    } catch (e) {
      setCancelling(false);
      setSubmitError(`Couldn't stop the run: ${(e as Error).message}`);
    }
  }

  function backToEditor() {
    setRunId(null);
    setStep(1);
  }

  function another() {
    setRunId(null);
    setResult(null);
    setSource("paste");
    setCode("");
    setFileName("");
    setTestInputs([]);
    setLangTouched(false);
    setLanguage("c");
    setCodeError(null);
    setSubmitError(null);
    setGoal("speed");
    setMethod("quick");
    setStep(1);
  }

  const reachable = (n: number) => !running && (n <= 3 || (n === 5 && !!result));

  return (
    <div className="mx-auto max-w-[1040px] space-y-8 pb-16 text-[15px]">
      <header className="space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <span className="eyebrow">Try as User</span>
          <Link href="/requirements/" className="text-[13px] text-muted underline-offset-2 hover:text-ink hover:underline">← Requirements Review</Link>
        </div>
        <h1 className="text-[30px] font-semibold leading-tight tracking-tight text-ink md:text-[36px]">Make your C/C++ code faster</h1>
        <p className="max-w-[640px] text-[16px] text-muted">
          Bring a program, tell us what matters, and we&apos;ll try to speed it up. Every change is compiled, compared with your original&apos;s output and timed before you see it.
        </p>
      </header>

      <Stepper current={step} reachable={reachable} onGo={setStep} />

      {dockerDown && (
        <Notice tone="warn" title="Docker isn't running">
          Optimizing needs Docker to compile and time code safely. Start Docker Desktop, then reload this page.
        </Notice>
      )}

      {/* ---------------------------------------------------------- 1 */}
      {step === 1 && (
        <section className="space-y-6" aria-labelledby="s1">
          <h2 id="s1" className="text-[22px] font-semibold tracking-tight">Which code should we optimize?</h2>
          <input id="file-input" ref={fileRef} type="file" accept=".c,.cpp,.cc,.cxx" className="sr-only" aria-label="Choose a C or C++ file" onChange={(e) => { const f = e.target.files?.[0]; if (f) pickFile(f); e.target.value = ""; }} />
          <div role="radiogroup" aria-label="Where your code comes from" className="grid gap-3 md:grid-cols-3">
            <RadioCard name="source" checked={source === "paste"} onChange={() => { setSource("paste"); setCodeError(null); }} icon="📋" title="Paste my code" desc="Type or paste any complete C or C++ program." />
            <RadioCard name="source" checked={source === "upload"} onChange={() => { setSource("upload"); setCodeError(null); }} icon="📁" title="Upload a file" desc=".c, .cpp, .cc or .cxx, up to 256 KB." />
            <RadioCard name="source" checked={source === "sample"} onChange={() => { setSource("sample"); setCodeError(null); }} icon="🧪" title="Try a sample" desc="Slow programs we prepared, ready to speed up." />
          </div>

          {source === "sample" && (
            <div className="space-y-4">
              <div role="radiogroup" aria-label="Sample program" className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {SAMPLES.map((s) => (
                  <RadioCard key={s.id} name="sample" checked={sampleId === s.id} onChange={() => setSampleId(s.id)} title={s.name} desc={s.desc} />
                ))}
              </div>
              <label className="flex flex-wrap items-center gap-2 text-[13.5px] text-muted">
                More samples:
                <select
                  value={SAMPLES.some((s) => s.id === sampleId) ? "" : sampleId}
                  onChange={(e) => e.target.value && setSampleId(e.target.value)}
                  className="rounded-[8px] border border-rule bg-surface px-3 py-2 text-[14px] text-ink"
                >
                  <option value="">Choose from all {programs?.length ?? 50}…</option>
                  {programs?.map((p) => <option key={p.id} value={p.id}>{p.id} ({CATEGORY_LABEL[p.category] || p.category})</option>)}
                </select>
              </label>
              <CodeEditor label="Sample program (read-only)" value={sampleCode} readOnly />
            </div>
          )}

          {source === "upload" && !code && (
            <label
              htmlFor="file-input"
              onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
              onDragLeave={() => setDragging(false)}
              onDrop={(e) => { e.preventDefault(); setDragging(false); const f = e.dataTransfer.files?.[0]; if (f) pickFile(f); }}
              className={cx("flex cursor-pointer flex-col items-center gap-2 rounded-[12px] border-2 border-dashed px-6 py-12 text-center transition-colors focus-within:ring-2 focus-within:ring-accent/40", dragging ? "border-accent bg-accent-soft" : "border-rule bg-surface hover:border-ink/30")}
            >
              <span className="text-[32px]" aria-hidden>📁</span>
              <span className="text-[16px] font-semibold">Drop a file here, or click to choose one</span>
              <span className="text-[13.5px] text-muted">.c, .cpp, .cc or .cxx · up to 256 KB</span>
            </label>
          )}

          {!isSample && (source === "paste" || code) && (
            <div className="space-y-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="flex flex-wrap items-center gap-3 text-[13.5px] text-muted">
                  {fileName && <span className="rounded-full bg-sunken px-3 py-1 font-medium text-ink">{fileName}</span>}
                  <span>{code ? `${code.split("\n").length} lines` : "Empty"}</span>
                  <span className="flex items-center gap-2">Language
                    <Segmented size="sm" value={language} onChange={(v) => { setLanguage(v); setLangTouched(true); }} options={[{ value: "c", label: "C" }, { value: "cpp", label: "C++" }]} />
                  </span>
                </div>
                <div className="flex gap-4 text-[13.5px]">
                  {source === "upload" && <button type="button" onClick={() => fileRef.current?.click()} className="font-medium text-info underline underline-offset-2">Choose a different file</button>}
                  <button type="button" disabled={!code} onClick={() => { setCode(""); setFileName(""); setCodeError(null); setLangTouched(false); }} className="font-medium text-info underline underline-offset-2 disabled:text-faint disabled:no-underline">Clear</button>
                </div>
              </div>
              <CodeEditor label="Your C or C++ code" value={code} onChange={editCode} placeholder={"#include <stdio.h>\n\nint main(void) {\n    // paste your program here\n    return 0;\n}"} />

              <Accordion title="Does your program read input? (optional)" hint="Give an example of what it reads, so it can be run and timed.">
                <p className="text-[13.5px] text-muted">
                  We run your original code on each example, remember its output, and only accept a faster version that prints exactly the same. A bigger example gives a more trustworthy timing. Leave empty if your program needs no input.
                </p>
                {testInputs.map((t, i) => (
                  <div key={i} className="space-y-1.5">
                    <div className="flex items-center justify-between text-[13px]">
                      <label htmlFor={`ex-${i}`} className="font-medium text-ink">Example input {i + 1}</label>
                      <button type="button" onClick={() => setTestInputs(testInputs.filter((_, j) => j !== i))} className="text-info underline underline-offset-2">Remove</button>
                    </div>
                    <textarea id={`ex-${i}`} value={t} rows={4} spellCheck={false} onChange={(e) => setTestInputs(testInputs.map((x, j) => (j === i ? e.target.value : x)))} className="w-full rounded-[8px] border border-rule bg-sunken p-3 font-mono text-[13px] outline-none focus:border-accent" placeholder={"5\n3 1 4 1 5"} />
                  </div>
                ))}
                {testInputs.length < MAX_TEST_INPUTS && (
                  <BigButton variant="ghost" onClick={() => setTestInputs([...testInputs, ""])}>+ Add an example input</BigButton>
                )}
              </Accordion>
            </div>
          )}

          {codeError && <Notice tone="bad">{codeError}</Notice>}
          <div className="flex justify-end"><BigButton onClick={goFromCode}>Continue →</BigButton></div>
        </section>
      )}

      {/* ---------------------------------------------------------- 2 */}
      {step === 2 && (
        <section className="space-y-6" aria-labelledby="s2">
          <h2 id="s2" className="text-[22px] font-semibold tracking-tight">What would you like to improve?</h2>
          <div role="radiogroup" aria-label="Goal" className="grid gap-3 sm:grid-cols-2">
            {GOALS.map((g) => <RadioCard key={g.key} name="goal" checked={goal === g.key} onChange={() => setGoal(g.key)} icon={g.icon} title={g.title} desc={g.desc} />)}
          </div>
          {goal === "custom" && (
            <div className="space-y-2">
              <label htmlFor="custom-goal" className="block text-[14px] font-medium">What should we focus on?</label>
              <textarea id="custom-goal" value={customGoal} onChange={(e) => setCustomGoal(e.target.value)} maxLength={600} rows={3} placeholder="For example: the inner loop is slow because it jumps around in memory." className="w-full rounded-[10px] border border-rule bg-surface p-3 text-[15px] outline-none focus:border-accent" />
              {guard && <Notice tone={guard.ok ? "good" : "bad"}>{guard.ok ? "Looks fine." : `That can't be used: ${guard.findings[0]?.rule ?? "it was flagged by the safety filter"}.`}</Notice>}
            </div>
          )}
          {goalProblem && <Notice tone="bad">{goalProblem}</Notice>}
          <div className="flex justify-between">
            <BigButton variant="ghost" onClick={() => setStep(1)}>← Back</BigButton>
            <BigButton onClick={() => !goalProblem && setStep(3)} disabled={!!goalProblem}>Continue →</BigButton>
          </div>
        </section>
      )}

      {/* ---------------------------------------------------------- 3 */}
      {step === 3 && (
        <section className="space-y-6" aria-labelledby="s3">
          <h2 id="s3" className="text-[22px] font-semibold tracking-tight">Ready to go?</h2>

          <dl className="grid gap-px overflow-hidden rounded-[12px] border border-rule bg-rule sm:grid-cols-3">
            {[
              ["Your code", isSample ? SAMPLES.find((s) => s.id === sampleId)?.name ?? sampleId : `${fileName || "Pasted code"} · ${activeLang === "c" ? "C" : "C++"} · ${activeCode.split("\n").length} lines`],
              ["Goal", GOALS.find((g) => g.key === goal)!.title],
              ["Checked against", isSample ? "Prepared test inputs" : testInputs.some((t) => t.trim()) ? `${testInputs.filter((t) => t.trim()).length} example input(s) you gave` : "Your program run with no input"],
            ].map(([k, v]) => (
              <div key={k} className="bg-surface p-4"><dt className="text-[12.5px] text-muted">{k}</dt><dd className="mt-0.5 text-[15px] font-medium text-ink">{v}</dd></div>
            ))}
          </dl>

          <div className="space-y-3">
            <h3 className="text-[16px] font-semibold">How should we do it?</h3>
            <div role="radiogroup" aria-label="Method" className="grid gap-3 sm:grid-cols-2">
              <RadioCard name="method" checked={method === "quick"} onChange={() => setMethod("quick")} icon="🚀" title="Quick tune" badge={<span className="rounded-full bg-sunken px-2 py-0.5 text-[11.5px] font-medium text-muted">Free · default</span>} desc={isSample ? "Tries compiler settings and built-in tricks for this sample. No AI, no cost." : "Tries compiler settings only, so your source stays untouched. No AI, no cost."} />
              <RadioCard name="method" checked={method === "smart"} onChange={() => keyAvailable && setMethod("smart")} disabled={health ? !keyAvailable : false} icon="🧠" title="Smart rewrite" badge={<span className="rounded-full bg-sunken px-2 py-0.5 text-[11.5px] font-medium text-muted">Uses AI</span>} desc={health && !keyAvailable ? "Needs an AI API key in the server's .env file, so it's unavailable right now." : "AI agents can restructure your code (loops, memory layout). Uses AI credits and takes longer."} />
            </div>
            {method === "quick" && goal !== "speed" && (
              <p className="text-[13px] text-muted">Note: your goal guides the Smart rewrite. Quick tune always looks for the fastest compiler settings.</p>
            )}
          </div>

          <Accordion title="Advanced settings" hint="How hard to try, and how strict to be">
            <fieldset className="space-y-2">
              <legend className="mb-1 text-[14px] font-semibold">How hard should we try?</legend>
              <div role="radiogroup" className="grid gap-3 sm:grid-cols-3">
                <RadioCard name="effort" checked={effort === 1} onChange={() => setEffort(1)} title="Fast" desc="1 attempt" />
                <RadioCard name="effort" checked={effort === 3} onChange={() => setEffort(3)} title="Standard" desc="Up to 3 attempts" />
                <RadioCard name="effort" checked={effort === 5} onChange={() => setEffort(5)} title="Thorough" desc="Up to 5 attempts" />
              </div>
            </fieldset>
            <label className="flex cursor-pointer items-start gap-3">
              <input type="checkbox" checked={strict} onChange={(e) => setStrict(e.target.checked)} className="mt-1 h-4 w-4 accent-[rgb(var(--accent))]" />
              <span>
                <span className="block text-[14.5px] font-medium">Be extra careful</span>
                <span className="block text-[13px] text-muted">Prefer small, low-risk changes over bold rewrites.</span>
              </span>
            </label>
          </Accordion>

          {submitError && <Notice tone="bad" title="We couldn't start the optimization">{submitError}</Notice>}
          <div className="flex flex-wrap items-center justify-between gap-3">
            <BigButton variant="ghost" onClick={() => setStep(2)}>← Back</BigButton>
            <BigButton onClick={optimize} disabled={submitting || dockerDown}>{submitting ? "Starting…" : "Optimize my code"}</BigButton>
          </div>
        </section>
      )}

      {/* ---------------------------------------------------------- 4 */}
      {step === 4 && (
        <>
          <ProgressView status={runStatus} events={events} maxAttempts={effort} startedAt={startedAt} queuePosition={queuePos} onCancel={cancel} cancelling={cancelling} />
          {submitError && <Notice tone="bad">{submitError}</Notice>}
        </>
      )}

      {/* ---------------------------------------------------------- 5 */}
      {step === 5 && result && outcome && (
        <section aria-labelledby="s5" className="space-y-6">
          <h2 id="s5" className="sr-only">Results</h2>
          <ResultsView run={result} outcome={outcome} fileName={resultFile} language={resultLang} onAnother={another} onBack={backToEditor} />
        </section>
      )}
      {step === 5 && !result && submitError && <Notice tone="bad">{submitError}</Notice>}
    </div>
  );
}
