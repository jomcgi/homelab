import { Route, Switch, Redirect } from "wouter";
import { TripProvider } from "./contexts/TripContext";
import { TripSummaryPage } from "./pages/TripSummaryPage";
import { TripTimeline } from "./pages/TripTimeline";
import { DayDetailPage } from "./pages/DayDetailPage";
import { NotFound } from "./pages/NotFound";

export default function App() {
  return (
    <Switch>
      {/* Default redirect to current trip */}
      <Route path="/">
        <Redirect to="/2025-liard-hot-springs" />
      </Route>

      {/* Trip timeline page - must come before summary to match first */}
      <Route path="/:trip/timeline">
        {(params) => (
          <TripProvider tripSlug={params.trip}>
            <TripTimeline />
          </TripProvider>
        )}
      </Route>

      {/* Day detail page - must come before summary to match first */}
      <Route path="/:trip/day/:dayNumber">
        {(params) => (
          <TripProvider tripSlug={params.trip}>
            {/* TRANSITION_HOOK: Page transition animation could be added here */}
            <DayDetailPage dayNumber={parseInt(params.dayNumber, 10)} />
          </TripProvider>
        )}
      </Route>

      {/* Trip summary page */}
      <Route path="/:trip">
        {(params) => (
          <TripProvider tripSlug={params.trip}>
            <TripSummaryPage />
          </TripProvider>
        )}
      </Route>

      {/* 404 */}
      <Route>
        <NotFound />
      </Route>
    </Switch>
  );
}
