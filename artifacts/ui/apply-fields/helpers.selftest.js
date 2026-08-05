/**
 * Lightweight self-test for apply field helper logic (no React).
 * Run: node --experimental-strip-types  (or copy assertions)
 *
 * This file mirrors key pure helpers for CI-friendly node assert.
 */
function toLibraryApplyKey(profileKey) {
  const k = (profileKey || "").trim().toLowerCase().replace(/^ats:/, "");
  if (!k || k === "resume_upload" || k === "submit_button" || k === "resume_path") return null;
  const map = {
    full_name: "full_name",
    email: "email",
    phone: "phone",
    linkedin: "linkedin_url",
    portfolio: "portfolio_url",
    github: "github_url",
    work_authorization: "work_authorized",
    needs_sponsorship: "needs_sponsorship",
    cover_letter: "answers.cover_letter",
  };
  return map[k] || (k.startsWith("answers.") ? k : null);
}

function mergeApplyPatch(current, libraryKey, value) {
  if (libraryKey.startsWith("answers.")) {
    const sub = libraryKey.slice("answers.".length);
    const answers = { ...(current.answers || {}), [sub]: value };
    return { ...current, answers };
  }
  return { ...current, [libraryKey]: value };
}

function groupIdForKey(key) {
  const basics = ["full_name", "email", "phone", "location"];
  const links = ["linkedin", "portfolio", "github"];
  const eligibility = ["work_authorization", "work_authorized", "needs_sponsorship"];
  const k = key.toLowerCase();
  if (basics.includes(k)) return "basics";
  if (links.includes(k)) return "links";
  if (eligibility.includes(k)) return "eligibility";
  return "other";
}

function assert(cond, msg) {
  if (!cond) throw new Error(msg || "assert failed");
}

assert(toLibraryApplyKey("linkedin") === "linkedin_url", "linkedin map");
assert(toLibraryApplyKey("portfolio") === "portfolio_url", "portfolio map");
assert(toLibraryApplyKey("cover_letter") === "answers.cover_letter", "cover letter");
assert(toLibraryApplyKey("resume_upload") === null, "skip resume");
assert(toLibraryApplyKey("first_name") === null, "skip partial name");

const merged = mergeApplyPatch({ email: "a@b.com", answers: {} }, "answers.cover_letter", "hi");
assert(merged.answers.cover_letter === "hi", "answers merge");
assert(merged.email === "a@b.com", "preserve email");

assert(groupIdForKey("email") === "basics");
assert(groupIdForKey("github") === "links");
assert(groupIdForKey("needs_sponsorship") === "eligibility");
assert(groupIdForKey("why_join_us") === "other");

console.log("apply-field-helpers.selftest OK");
