import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiGet, apiPut } from "@/lib/api/client";

export interface Profile {
  full_name: string;
  phone: string | null;
  email: string;
  timezone: string;
  role: string | null;
  clearance: string | null;
}

export function useProfile() {
  return useQuery({
    queryKey: ["profile"],
    queryFn: () => apiGet<Profile>("/v1/profile"),
  });
}

export function useSaveProfile() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (
      profile: Pick<Profile, "full_name" | "phone" | "email" | "timezone">,
    ) => apiPut<Profile, typeof profile>("/v1/profile", profile),
    onSuccess: (profile) => {
      queryClient.setQueryData(["profile"], profile);
      queryClient.invalidateQueries({ queryKey: ["members", "me"] });
    },
  });
}
