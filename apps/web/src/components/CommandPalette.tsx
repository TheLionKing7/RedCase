import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "@tanstack/react-router";
import {
  Archive,
  Bot,
  CalendarClock,
  Command as CommandIcon,
  Home,
  LayoutGrid,
  MessageSquare,
  Search,
  Settings2,
  ShieldCheck,
  Sparkles,
  Users,
  Vault,
} from "lucide-react";
import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandShortcut,
} from "@/components/ui/command";

type PaletteProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onAssistant: () => void;
  onToggleDensity: () => void;
};
type PaletteCommand = {
  id: string;
  label: string;
  detail: string;
  keywords: string;
  icon: typeof Home;
  action: () => void;
  shortcut?: string;
};

export function CommandPalette({
  open,
  onOpenChange,
  onAssistant,
  onToggleDensity,
}: PaletteProps) {
  const navigate = useNavigate();
  const [recent, setRecent] = useState<string[]>(() => {
    try {
      return JSON.parse(
        localStorage.getItem("redcase.palette.recent") ?? "[]",
      ) as string[];
    } catch {
      return [];
    }
  });
  const go = (id: string, path: string) => {
    navigate({ to: path });
    remember(id);
    onOpenChange(false);
  };
  const remember = (id: string) =>
    setRecent((current) => {
      const next = [id, ...current.filter((item) => item !== id)].slice(0, 5);
      localStorage.setItem("redcase.palette.recent", JSON.stringify(next));
      return next;
    });
  const commands = useMemo<PaletteCommand[]>(
    () => [
      {
        id: "home",
        label: "Go to Home",
        detail: "Inbox and priorities",
        keywords: "home inbox priorities",
        icon: Home,
        action: () => go("home", "/home"),
      },
      {
        id: "workbench",
        label: "Open Workbench",
        detail: "Analysis and drafting",
        keywords: "workbench analysis drafting smartbrief",
        icon: Sparkles,
        action: () => go("workbench", "/workbench"),
      },
      {
        id: "search",
        label: "Cross-vault search",
        detail: "Search Internal Briefs and Juris OS together",
        keywords: "vault search research jurisprudence",
        icon: Search,
        action: () => go("search", "/search"),
      },
      {
        id: "tracker",
        label: "Open Tracker",
        detail: "Deadlines and court diary",
        keywords: "tracker deadlines court diary",
        icon: CalendarClock,
        action: () => go("tracker", "/tracker"),
      },
      {
        id: "channels",
        label: "Open Channels",
        detail: "Matter rooms and firm conversations",
        keywords: "messenger channels chat",
        icon: MessageSquare,
        action: () => go("channels", "/channels"),
      },
      {
        id: "access",
        label: "Access & Request",
        detail: "Request or review document grants",
        keywords: "access request grant permissions",
        icon: ShieldCheck,
        action: () => go("access", "/access-requests"),
      },
      {
        id: "contacts",
        label: "Firm directory",
        detail: "Find a colleague",
        keywords: "contacts people team members",
        icon: Users,
        action: () => go("contacts", "/contacts"),
      },
      {
        id: "archived",
        label: "Archived channels",
        detail: "Read-only concluded matters",
        keywords: "archive concluded read only",
        icon: Archive,
        action: () => go("archived", "/channels"),
      },
      {
        id: "assistant",
        label: "Open Assistant",
        detail: "Grounded drafting companion",
        keywords: "assistant ai help",
        icon: Bot,
        action: () => {
          remember("assistant");
          onOpenChange(false);
          onAssistant();
        },
      },
      {
        id: "density",
        label: "Toggle workspace density",
        detail: "Switch comfortable or compact layout",
        keywords: "compact comfortable density appearance",
        icon: Settings2,
        action: () => {
          remember("density");
          onOpenChange(false);
          onToggleDensity();
        },
      },
    ],
    [onAssistant, onOpenChange],
  );
  const recentCommands = recent
    .map((id) => commands.find((command) => command.id === id))
    .filter((command): command is PaletteCommand => Boolean(command));
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        onOpenChange(!open);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open, onOpenChange]);
  return (
    <CommandDialog
      open={open}
      onOpenChange={onOpenChange}
      title="Command palette"
      description="Navigate RedCase and run workspace actions."
    >
      <CommandInput placeholder="Search RedCase…" />
      <CommandList>
        <CommandEmpty>No matching commands.</CommandEmpty>
        {recentCommands.length > 0 && (
          <CommandGroup heading="Recent">
            {recentCommands.map((command) => (
              <PaletteItem key={command.id} command={command} />
            ))}
          </CommandGroup>
        )}
        <CommandGroup heading="Navigate">
          {commands.slice(0, 8).map((command) => (
            <PaletteItem key={command.id} command={command} />
          ))}
        </CommandGroup>
        <CommandGroup heading="Quick actions">
          {commands.slice(8).map((command) => (
            <PaletteItem key={command.id} command={command} />
          ))}
        </CommandGroup>
      </CommandList>
      <div className="border-t border-border px-3 py-2 text-[10px] text-muted-foreground">
        <CommandIcon className="mr-1 inline size-3" /> Use arrows to move ·
        Enter to select · Esc to close
      </div>
    </CommandDialog>
  );
}

function PaletteItem({ command }: { command: PaletteCommand }) {
  const Icon = command.icon;
  return (
    <CommandItem
      value={`${command.label} ${command.keywords}`}
      onSelect={command.action}
    >
      <Icon className="text-steel" />
      <span>
        <strong className="block">{command.label}</strong>
        <small className="text-muted-foreground">{command.detail}</small>
      </span>
      {command.shortcut && (
        <CommandShortcut>{command.shortcut}</CommandShortcut>
      )}
    </CommandItem>
  );
}
