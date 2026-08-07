export function StandaloneMessage({ children }: { children: string }) {
  return <main className="standalone-message" role="status">{children}</main>;
}
