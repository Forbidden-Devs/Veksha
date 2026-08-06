import { Fragment, type ReactNode } from "react";

function inlineMarkup(line: string): ReactNode[] {
  return line.split(/(\*\*.+?\*\*)/g).filter(Boolean).map((part, index) => (
    part.startsWith("**") && part.endsWith("**")
      ? <strong key={index}>{part.slice(2, -2)}</strong>
      : <Fragment key={index}>{part}</Fragment>
  ));
}

/** Render the learning API's tiny emphasis dialect as React, never HTML. */
export function RichText({ text }: { text: string }) {
  return text.split(/\r?\n/).map((line, index) => (
    <Fragment key={`${index}:${line}`}>
      {index > 0 && <br />}
      {inlineMarkup(line)}
    </Fragment>
  ));
}
