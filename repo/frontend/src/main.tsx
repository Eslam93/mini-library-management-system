import { StrictMode } from "react"
import { createRoot } from "react-dom/client"
import { BrowserRouter } from "react-router"

import { App } from "@/app"
import { ErrorBoundary } from "@/components/states/error-boundary"
import { AppProviders } from "@/providers"

import "./index.css"

const root = document.getElementById("root")
if (!root) throw new Error("The page has no #root element.")

createRoot(root).render(
  <StrictMode>
    <ErrorBoundary>
      <AppProviders>
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </AppProviders>
    </ErrorBoundary>
  </StrictMode>,
)
