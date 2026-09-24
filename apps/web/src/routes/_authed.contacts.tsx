import { createFileRoute } from "@tanstack/react-router";
import { CollaborationWorkspace } from "@/components/CollaborationWorkspace";
export const Route = createFileRoute("/_authed/contacts")({ component: () => <CollaborationWorkspace section="contacts" /> });
