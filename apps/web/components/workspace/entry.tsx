"use client";

import type { WorkspaceOut } from "@devgrill/api-client";
import { useState } from "react";
import { createDemoSource } from "./demo-source";
import { createLiveSource } from "./live-source";
import { Workspace } from "./workspace";

/** A real incident: the API, the event stream and the gateway's sockets. */
export function LiveWorkspace({ info, briefingHref }: { info: WorkspaceOut; briefingHref: string }) {
  const [source] = useState(() => createLiveSource(info));
  return <Workspace source={source} briefingHref={briefingHref} />;
}

/** The design shell with canned data: design QC, accessibility and keyboard tests. */
export function DemoWorkspace({ tutorial = false }: { tutorial?: boolean }) {
  const [source] = useState(() => createDemoSource({ tutorial }));
  return <Workspace source={source} briefingHref="/drills/caching/big-sale-meltdown" />;
}
