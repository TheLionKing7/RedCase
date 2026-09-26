import { QueryClient } from "@tanstack/react-query";
import { createRouter } from "@tanstack/react-router";
import { routeTree } from "./routeTree.gen";
import { processAuthSessionFromUrl } from "@/lib/auth/supabase";

export const getRouter = () => {
  if (typeof window !== "undefined") processAuthSessionFromUrl();

  const queryClient = new QueryClient();

  const router = createRouter({
    routeTree,
    context: { queryClient },
    scrollRestoration: true,
    defaultPreloadStaleTime: 0,
  });

  return router;
};
