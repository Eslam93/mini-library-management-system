/**
 * Imports every page's module once. The app loads each page from its own
 * file, and the first import of one compiles its whole module graph, which
 * can take seconds on a busy machine. A test file that renders the whole app
 * calls this in beforeAll, so that time stays out of each test's time limit;
 * the app's own imports then reuse the compiled modules.
 */
export async function preloadPages() {
  const pages = import.meta.glob("/src/pages/*-page.tsx")
  await Promise.all(Object.values(pages).map((load) => load()))
}
