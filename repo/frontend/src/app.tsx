import { lazy, Suspense, type ComponentType } from "react"
import { Route, Routes } from "react-router"

import type { ReactNode } from "react"

import { AppShell } from "@/components/layout/app-shell"
import { LoadingState } from "@/components/states/loading-state"
import { RequireRole, RoleHome } from "@/features/auth/require-role"
import { RequireSignIn } from "@/features/auth/require-sign-in"
import { NotFoundPage } from "@/pages/not-found-page"
import { SignInPage } from "@/pages/sign-in-page"

/** A page whose code loads in its own file the first time it is opened. */
function lazyPage<Name extends string>(
  load: () => Promise<Record<Name, ComponentType>>,
  name: Name,
) {
  return lazy(() => load().then((module) => ({ default: module[name] })))
}

// A first visit downloads the shell and the one page it lands on. Sign-in and
// the not-found page are small and needed before any page, so they stay in the
// main file; the shell shows a loading state while a page's file arrives.
const ActivityPage = lazyPage(() => import("@/pages/activity-page"), "ActivityPage")
const BookDetailPage = lazyPage(() => import("@/pages/book-detail-page"), "BookDetailPage")
const CatalogPage = lazyPage(() => import("@/pages/catalog-page"), "CatalogPage")
const CirculationPage = lazyPage(() => import("@/pages/circulation-page"), "CirculationPage")
const DashboardPage = lazyPage(() => import("@/pages/dashboard-page"), "DashboardPage")
const HistoryPage = lazyPage(() => import("@/pages/history-page"), "HistoryPage")
const MemberDetailPage = lazyPage(() => import("@/pages/member-detail-page"), "MemberDetailPage")
const MembersPage = lazyPage(() => import("@/pages/members-page"), "MembersPage")
const MyLoansPage = lazyPage(() => import("@/pages/my-loans-page"), "MyLoansPage")
const PrivacyPage = lazyPage(() => import("@/pages/notices-page"), "PrivacyPage")
const TermsPage = lazyPage(() => import("@/pages/notices-page"), "TermsPage")

function Loading({ children }: { children: ReactNode }) {
  return <Suspense fallback={<LoadingState rows={3} label="Loading the page" />}>{children}</Suspense>
}

export function App() {
  return (
    <Routes>
      <Route path="sign-in" element={<SignInPage />} />
      {/* Readable without signing in: a sign-in provider links to them from its consent screen.
          They load from their own file, and they sit outside the shell, so they carry their own
          loading state. */}
      <Route path="privacy" element={<Loading><PrivacyPage /></Loading>} />
      <Route path="terms" element={<Loading><TermsPage /></Loading>} />
      <Route element={<RequireSignIn />}>
        <Route element={<AppShell />}>
          <Route index element={<RoleHome />} />
          <Route path="catalog" element={<CatalogPage />} />
          <Route path="books/:bookId" element={<BookDetailPage />} />
          <Route element={<RequireRole role="staff" />}>
            <Route path="dashboard" element={<DashboardPage />} />
            <Route path="circulation" element={<CirculationPage />} />
            <Route path="members" element={<MembersPage />} />
            <Route path="members/:memberId" element={<MemberDetailPage />} />
            <Route path="activity" element={<ActivityPage />} />
          </Route>
          <Route element={<RequireRole role="member" />}>
            <Route path="my-loans" element={<MyLoansPage />} />
            <Route path="history" element={<HistoryPage />} />
          </Route>
          <Route path="*" element={<NotFoundPage />} />
        </Route>
      </Route>
    </Routes>
  )
}
