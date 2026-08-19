/* Parity check: scheduling/sim.js (browser port) must reproduce the numbers
 * experiment/evaluate.py produced during the real AlphaEvolve run.
 *
 *   node scripts/check_scheduling_sim.mjs
 */
import {readFileSync} from "node:fs";
import {fileURLToPath} from "node:url";
import {dirname, join} from "node:path";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const src = readFileSync(join(ROOT, "scheduling", "sim.js"), "utf8");
const sim = await import("data:text/javascript," + encodeURIComponent(src));

const variants = JSON.parse(readFileSync(join(ROOT, "data", "variants.json"), "utf8"));
const trace = JSON.parse(readFileSync(join(ROOT, "traces", "evolution_trace.json"), "utf8"));
const bests = trace.candidates.filter(c => c.new_best);
const best = bests[bests.length - 1];

const policy = id => sim.POLICIES.find(p => p.id === id);
let failures = 0;

function check(what, got, want, tol = 0.05) {
  const ok = Math.abs(got - want) <= tol;
  if (!ok) failures++;
  console.log(`  ${ok ? "PASS" : "FAIL"}  ${what}: ${got.toLocaleString()} (evaluate.py: ${want.toLocaleString()})`);
}

console.log("scheduling/sim.js vs the recorded AlphaEvolve run");

const base = sim.scoreAll(variants.instances, policy("baseline").make);
check("baseline score (mean of 3 instances)", base.mean, trace.baseline.score);
check("baseline parcels, primary network", base.per[0].parcels, trace.baseline.primary.parcels);
check("baseline runs, primary network", base.per[0].runs, trace.baseline.primary.runs, 0);

const evo = sim.scoreAll(variants.instances, policy("evolved").make);
check(`evolved score (candidate #${best.idx})`, evo.mean, best.score);
check("evolved parcels, primary network", evo.per[0].parcels, best.primary.parcels);
check("evolved runs, primary network", evo.per[0].runs, best.primary.runs, 0);

// the genome the GA explainer searches must contain the evolved rule exactly
const gen = sim.scoreAll(variants.instances, net => sim.genomePolicy(net, sim.EVOLVED_GENOME));
check(`genome [${sim.EVOLVED_GENOME}] == candidate #${best.idx}`, gen.mean, best.score);

// the schedule the UI draws must be the same schedule evaluate.py recorded
const got = base.per[0].schedule[0].segments;
const want = trace.baseline.primary.schedule[0].segments;
const sameShape = got.length === want.length && got.every((s, i) =>
  s.type === want[i].type && s.at === want[i].at &&
  Math.abs(s.t0 - want[i].t0) < 0.05 && Math.abs(s.t1 - want[i].t1) < 0.05);
console.log(`  ${sameShape ? "PASS" : "FAIL"}  T01 baseline schedule: ${got.length} segments match the trace`);
if (!sameShape) failures++;

// every policy must produce a valid, non-degenerate schedule on every instance
for (const p of sim.POLICIES) {
  const r = sim.scoreAll(variants.instances, p.make);
  const bad = r.per.some(x => !(x.parcels > 0) || x.runs < 1);
  if (bad) failures++;
  console.log(`  ${bad ? "FAIL" : "PASS"}  policy "${p.id}" runs on all 3 instances: ` +
              `${Math.round(r.mean).toLocaleString()} parcels/shift`);
}

console.log(failures ? `\n${failures} check(s) FAILED` : "\nall checks passed");
process.exit(failures ? 1 : 0);
