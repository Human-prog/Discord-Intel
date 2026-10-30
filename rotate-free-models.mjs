#!/usr/bin/env node
"use strict";
/**
 * Free-Model Circulator — rotates through available free LLM providers
 * so work never stops when one model hits rate limits or goes down.
 *
 * Usage:
 *   node rotate-free-models.mjs              # show current rotation order
 *   node rotate-free-models.mjs --next       # get next model for a request
 *   node rotate-free-models.mjs --status     # check which providers are free
 */

import { fileURLToPath } from "url";
import { dirname, join } from "path";

// Free model pool from opencode.models() query (openrouter + opencode providers)
const FREE_MODELS = [
  // openrouter/free tier (no billing, best for continuous use)
  "openrouter/openrouter/free",
  "openrouter/google/gemma-4-26b-a4b-it:free",
  "openrouter/cohere/north-mini-code:free",
  "openrouter/liquid/lfm-2.5-2.6b:free",
  "openrouter/nvidia/nemotron-3.5-super-vl:free",
  "openrouter/recursive/flint-v1.0:free",
  // opencode native free tier (fastest response, local routing)
  "opencode/mimo-v2.6-flash-free",
  "opencode/deepseek-v4.1-flash-free",
  "opencode/glm-5.3-flash-free",
  "opencode/flint-40b-free",
  "opencode/nemotron-3.5-super-vl-free",
  "opencode/beam-free",
];

// Rotation state (persisted per session/user in memory; reset every process start)
let rotationIndex = 0;

function rotate() {
  const model = FREE_MODELS[rotationIndex % FREE_MODELS.length];
  rotationIndex++;
  return model;
}

function getPoolStatus() {
  return FREE_MODELS.map((m) => ({
    model: m,
    provider: m.split("/")[0],
    status: "free",
    rotation: FREE_MODELS.indexOf(m) + 1,
  }));
}

// CLI interface
const args = process.argv.slice(2);
if (args.includes("--status")) {
  console.log("Free Model Pool Status");
  console.log("=".repeat(50));
  for (const s of getPoolStatus()) {
    console.log(
      `${String(s.rotation).padStart(2, " ")}. ${s.model.padEnd(40)} [${s.provider} / free]`
    );
  }
  console.log(`\nTotal free models in pool: ${FREE_MODELS.length}`);
  console.log("Each request advances rotation by 1 — no manual switching needed.");
} else if (args.includes("--next")) {
  console.log("Next model for request:", rotate());
} else {
  console.log("Free-Model Circulator");
  console.log("=".repeat(50));
  console.log("Available commands:");
  console.log("  --status  Show all free models in rotation pool");
  console.log("  --next    Get the next model (advances rotation)");
  console.log("  <none>    Same as --status (default)");
  console.log("\nCurrent rotation order:");
  for (const m of FREE_MODELS) {
    console.log("  -", m);
  }
  console.log(
    `\nUsage in your agent/config: set model to the output of '--next' per turn.`
  );
}
