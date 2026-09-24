import { createFileRoute } from "@tanstack/react-router";
import { CollaborationWorkspace } from "@/components/CollaborationWorkspace";
export const Route = createFileRoute("/_authed/pins")({ component: () => <CollaborationWorkspace section="pins" /> });
