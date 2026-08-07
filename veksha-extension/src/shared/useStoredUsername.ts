import { useEffect, useState } from "react";
import { CONFIG } from "./config";

export function useStoredUsername(): string | null {
  const [username, setUsername] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    chrome.storage.local.get(CONFIG.STORAGE_KEY_USERNAME).then((values) => {
      if (active) setUsername(String(values[CONFIG.STORAGE_KEY_USERNAME] ?? "") || null);
    });
    return () => { active = false; };
  }, []);

  return username;
}
