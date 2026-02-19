import { useMemo } from "react";

/**
 * Derives a flat list of artifacts from the messages array.
 * Returns { artifact, id, msgTime, msgId } for each found artifact.
 */
export function useSessionArtifacts(messages) {
  return useMemo(() => {
    const list = [];
    for (const m of messages) {
      if (m.artifact) {
        list.push({
          artifact: m.artifact,
          id: `${m.id}-1`,
          msgTime: m.time || "",
          msgId: m.id,
        });
      }
      if (m.artifact2) {
        list.push({
          artifact: m.artifact2,
          id: `${m.id}-2`,
          msgTime: m.time || "",
          msgId: m.id,
        });
      }
    }
    return list;
  }, [messages]);
}
