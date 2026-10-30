// Structural inputs keep this boundary testable without starting Electron.
export function trustedSender(event: {sender: unknown; senderFrame: unknown}, owner: {webContents: {mainFrame: {url: string}}; isDestroyed(): boolean} | null, expectedUrl: string): boolean {
  return !!owner && !owner.isDestroyed() && event.sender === owner.webContents && event.senderFrame === owner.webContents.mainFrame && owner.webContents.mainFrame.url === expectedUrl;
}
