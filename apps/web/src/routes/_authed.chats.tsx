import { createFileRoute } from "@tanstack/react-router";
import { CollaborationWorkspace } from "@/components/CollaborationWorkspace";
export const Route = createFileRoute("/_authed/chats")({ component: () => <CollaborationWorkspace section="chats" /> });
