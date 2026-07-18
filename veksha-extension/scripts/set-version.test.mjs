import assert from "node:assert/strict";
import test from "node:test";

import { nextVersion, parseVersion } from "./set-version.mjs";

test("parses a stable three-part version", () => {
  assert.deepEqual(parseVersion("12.34.56"), [12, 34, 56]);
});

test("increments patch, minor, and major versions", () => {
  assert.equal(nextVersion("1.2.3", "patch"), "1.2.4");
  assert.equal(nextVersion("1.2.3", "minor"), "1.3.0");
  assert.equal(nextVersion("1.2.3", "major"), "2.0.0");
});

test("accepts an explicit version", () => {
  assert.equal(nextVersion("1.2.3", "4.5.6"), "4.5.6");
});

test("rejects invalid and prerelease versions", () => {
  assert.throws(() => parseVersion("1.2"), /Invalid version/);
  assert.throws(() => parseVersion("1.2.3-beta.1"), /Invalid version/);
  assert.throws(() => nextVersion("1.2.3", "banana"), /Unknown bump/);
});
