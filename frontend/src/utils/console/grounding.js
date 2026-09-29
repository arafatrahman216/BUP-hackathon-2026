/**
 * "The AI never invents numbers": every number in an AI answer must appear in the facts
 * the engine gave it. Small counts (≤ 10) are allowed. If the check fails, show the template.
 */

const NUMBER = /\d[\d,]*(?:\.\d+)?/g

function numbersIn(text) {
  return (String(text).match(NUMBER) || []).map((n) => Number(n.replace(/,/g, ''))).filter((n) => !Number.isNaN(n))
}

export function isGrounded(answer, facts) {
  const allowed = new Set(numbersIn(JSON.stringify(facts)))
  return numbersIn(answer).every((n) => n <= 10 || allowed.has(n) || allowed.has(Math.round(n)))
}

export const ASK_SYSTEM =
  'You explain fuel shipment recommendations to a fuel operations operator. The network is simulated. ' +
  'Use ONLY the facts provided. Never invent or estimate numbers that are not in the facts. ' +
  'Answer in at most three short, plain sentences. No lists, no headings.'

export function askPrompt(facts, question) {
  const q = question === 'why' ? 'Why is this shipment recommended?' : question
  return `Facts (JSON):\n${JSON.stringify(facts)}\n\nOperator question: ${q}`
}
