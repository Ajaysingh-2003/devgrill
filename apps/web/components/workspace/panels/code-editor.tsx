"use client";

import { python } from "@codemirror/lang-python";
import { HighlightStyle, syntaxHighlighting } from "@codemirror/language";
import { EditorState } from "@codemirror/state";
import { EditorView, keymap } from "@codemirror/view";
import { tags } from "@lezer/highlight";
import { basicSetup } from "codemirror";
import { useEffect, useLayoutEffect, useRef } from "react";

// Colours come from the design tokens (CSS variables), so both themes stay in contrast.
const highlight = HighlightStyle.define([
  { tag: [tags.keyword, tags.controlKeyword, tags.operatorKeyword], color: "var(--chart-7)" },
  { tag: [tags.string, tags.special(tags.string)], color: "var(--chart-3)" },
  { tag: [tags.comment, tags.lineComment], color: "var(--text-subtle)", fontStyle: "italic" },
  { tag: [tags.number, tags.bool, tags.null], color: "var(--chart-5)" },
  { tag: [tags.function(tags.variableName), tags.function(tags.propertyName)], color: "var(--chart-1)" },
  { tag: [tags.definition(tags.variableName), tags.className], color: "var(--chart-2)" },
]);

const theme = EditorView.theme({
  "&": { height: "100%", backgroundColor: "var(--sunken)", color: "var(--text)" },
  ".cm-content": { fontFamily: "var(--font-code), ui-monospace, monospace", caretColor: "var(--text)" },
  ".cm-gutters": { backgroundColor: "var(--surface)", color: "var(--text-subtle)", border: "none" },
  ".cm-activeLine": { backgroundColor: "var(--raised)" },
  ".cm-activeLineGutter": { backgroundColor: "var(--raised)" },
  "&.cm-focused .cm-selectionBackground, .cm-selectionBackground": { backgroundColor: "var(--brand-subtle)" },
  ".cm-cursor": { borderLeftColor: "var(--text)" },
});

/** The source editor. Loaded with the Code panel only (CodeMirror is sizeable). */
export default function CodeEditor({
  path,
  value,
  onChange,
  onSave,
  onDeploy,
}: {
  path: string;
  value: string;
  onChange: (value: string) => void;
  onSave: () => void;
  onDeploy: () => void;
}) {
  const host = useRef<HTMLDivElement>(null);
  const view = useRef<EditorView | null>(null);
  const handlers = useRef({ onChange, onSave, onDeploy });
  useLayoutEffect(() => {
    handlers.current = { onChange, onSave, onDeploy };
  });

  // One editor per file: undo history belongs to the file.
  useEffect(() => {
    if (!host.current) return;
    const editor = new EditorView({
      parent: host.current,
      state: EditorState.create({
        doc: value,
        extensions: [
          basicSetup,
          path.endsWith(".py") ? python() : [],
          syntaxHighlighting(highlight),
          theme,
          EditorView.contentAttributes.of({ "aria-label": `Source of ${path}` }),
          keymap.of([
            { key: "Mod-s", preventDefault: true, run: () => (handlers.current.onSave(), true) },
            { key: "Mod-Enter", preventDefault: true, run: () => (handlers.current.onDeploy(), true) },
          ]),
          EditorView.updateListener.of((update) => {
            if (update.docChanged) handlers.current.onChange(update.state.doc.toString());
          }),
        ],
      }),
    });
    view.current = editor;
    return () => {
      editor.destroy();
      view.current = null;
    };
    // The document is seeded once per file; later edits come from the editor itself.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path]);

  return <div ref={host} className="h-full min-h-0 overflow-hidden" data-hotkeys="off" />;
}
