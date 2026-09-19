// A canary for the verify-on-finish Stop hook, not a test of anything in the product.
// To prove the hook fires live: delete one of the expect lines below, end a turn, and the hook
// must block with this file's name. Then restore the file.
// It stays committed so the hook always has a file to be tried on by hand. No runner executes it.
test("the stop hook canary", () => {
  expect(1).toBe(1);
  expect(2).toBe(2);
});
