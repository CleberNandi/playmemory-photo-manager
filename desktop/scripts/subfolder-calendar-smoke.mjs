/* global process, console, setTimeout, clearTimeout */
// Standalone Electron test entry: production main/preload/renderer, temporary data only.
import {app, dialog} from "electron";
import {execFileSync} from "node:child_process";
import {mkdtempSync, mkdirSync, readFileSync, rmSync, statSync, unlinkSync, writeFileSync} from "node:fs";
import {tmpdir} from "node:os";
import {join} from "node:path";
import {fileURLToPath, URL} from "node:url";

const work = mkdtempSync(join(tmpdir(), "pm-subfolder-calendar-"));
process.once("exit", () => rmSync(work, {recursive:true, force:true}));
const profile = join(work, "profile"), root = join(work, "Synthetic");
mkdirSync(profile, {mode:0o700});
mkdirSync(root);
mkdirSync(join(root, "teste"));
const png = join(root, "teste", "photo (2).png");
const jpg = join(root, "teste", "capture.jpg");
execFileSync("uv", ["run", "--offline", "python", "-c", `
from PIL import Image
from pathlib import Path
import sys
root = Path(sys.argv[1])
Image.new('RGB', (80, 40), (180, 20, 30)).save(root / 'photo (2).png')
Image.new('RGB', (80, 40), (25, 100, 210)).save(root / 'teste' / 'photo (2).png')
Image.new('RGB', (80, 40), (70, 130, 20)).save(root / 'keep.png')
exif = Image.Exif()
exif[34665] = {36867: '2024:02:29 23:30:00', 36881: '-03:00'}
Image.new('RGB', (80, 40), (30, 180, 60)).save(root.parent / 'capture-fixture.jpg', exif=exif)
`, root], {cwd:fileURLToPath(new URL("../../", import.meta.url))});
const originals = [png,join(root,"keep.png")].map(file => ({file, bytes:readFileSync(file), mtime:statSync(file).mtimeMs}));
app.setPath("userData", profile);
app.setPath("sessionData", profile);

// Only native selection/description is replaced. All catalog/media requests use real IPC.
let fullLocation, selected = false;
dialog.showOpenDialog = async (_window, options) => {
  if (options.properties.join() !== "openDirectory" || selected) throw new Error("Unexpected selection");
  selected = true;
  return {canceled:false, filePaths:[root]};
};
dialog.showMessageBox = async (_window, options) => {
  if (options.title !== "Localização do arquivo") throw new Error("Unexpected native dialog");
  fullLocation = options.detail;
  return {response:0, checkboxChecked:false};
};
const watchdog = setTimeout(() => {
  console.error("SUBFOLDER/CALENDAR FAIL: timeout");
  process.exitCode = 1;
  app.quit();
}, 60_000);

app.on("browser-window-created", (_event, window) => {
  window.webContents.once("did-finish-load", async () => {
    const evaluate = code => window.webContents.executeJavaScript(code);
    const wait = async expression => {
      for (let i=0; i<200; i++) {
        if (await evaluate(expression)) return;
        await new Promise(resolve => setTimeout(resolve, 50));
      }
      throw new Error(`Timeout: ${expression}`);
    };
    const click = async label => {
      const match = `b.textContent===${JSON.stringify(label)}&&!b.disabled`;
      await wait(`Array.from(document.querySelectorAll('button')).some(b=>${match})`);
      await evaluate(`Array.from(document.querySelectorAll('button')).find(b=>${match}).click()`);
    };
    try {
      await wait('document.querySelector(".status-panel h2")?.textContent==="Sua biblioteca está vazia"');
      await click("+ Adicionar pastas");
      await wait('document.querySelectorAll(".media-card").length===3');
      await wait('document.querySelector(".folder-import-panel")?.textContent.includes("Pasta carregada")');
      const before = await evaluate('window.photoManager.listGallery({pageSize:24})');
      const find = path => before.items.find(item => item.representative_location.relative_path === path);
      const available = find("teste/photo (2).png"), parent = find("photo (2).png");
      if (available.asset_id === parent.asset_id) throw new Error("Namesakes merged");
      unlinkSync(join(root, "photo (2).png")); // Remove only the harness-owned synthetic fixture.
      await evaluate("window.photoManager.refreshFolders()");
      await wait(`!document.querySelector('[data-asset-id="${parent.asset_id}"]')&&document.querySelectorAll('.media-card').length===2`);
      const parentDetails=await evaluate(`window.photoManager.getAssetDetails(${JSON.stringify(parent.asset_id)})`);
      if(parentDetails.status!=="ready"||parentDetails.details.availability!=="unavailable")throw new Error("Missing occurrence history lost");

      const mtimeDate = new Date(originals[0].mtime);
      const mtimeYear = String(mtimeDate.getFullYear());
      const mtimeMonthNumber = String(mtimeDate.getMonth() + 1).padStart(2, "0");
      const mtimeDay = `${mtimeYear}-${mtimeMonthNumber}-${String(mtimeDate.getDate()).padStart(2, "0")}`;
      await click("Calendário");
      await wait(`Array.from(document.querySelectorAll(".calendar-years button")).some(b=>b.textContent===${JSON.stringify(`${mtimeYear}2 foto(s)`)})`);
      if (!await evaluate('Array.from(document.querySelectorAll("button")).some(b=>b.textContent==="Calendário"&&b.getAttribute("aria-pressed")==="true")')) throw new Error("Fallback gallery left calendar mode");
      console.log("MTIME FALLBACK CALENDAR PASS: PNGs without EXIF capture date appear in Calendar under modification year");

      // Add a capture and a new grandchild while open; select only the parent once.
      writeFileSync(jpg, readFileSync(join(work, "capture-fixture.jpg")));
      const deeper = join(root, "teste", "filha");
      mkdirSync(deeper);
      const late = join(deeper, "late.png");
      writeFileSync(late, readFileSync(png));
      for (const file of [jpg,late]) originals.push({file,bytes:readFileSync(file),mtime:statSync(file).mtimeMs});
      await wait('window.photoManager.listGallery({pageSize:24}).then(p=>p.items.length===4)');
      const updated = await evaluate('window.photoManager.listGallery({pageSize:24})');
      const capture = updated.items.find(item=>item.representative_location.relative_path==="teste/capture.jpg");
      if (updated.roots.length!==1) throw new Error("Descendants required another root");
      await click("Biblioteca");
      await wait('document.querySelectorAll(".media-card").length===4 && !document.querySelector(".content").hidden');
      console.log("RECURSION PASS: one parent selection; new JPEG and grandchild PNG discovered automatically");

      for (const view of ["Biblioteca", "Pastas"]) {
        if (view === "Pastas") {
          await click("Pastas");
          await wait('!!document.querySelector(".folder-card")');
          await click("Synthetic");
          await wait('document.querySelectorAll(".media-card").length===4');
          if (!await evaluate(`!!document.querySelector('[data-asset-id="${available.asset_id}"]')`)) throw new Error("Parent view omitted descendants");
          await wait('Array.from(document.querySelectorAll(".folder-card")).some(b=>b.textContent.includes("teste"))');
          await evaluate('Array.from(document.querySelectorAll(".folder-card")).find(b=>b.textContent.includes("teste")).click()');
          await wait('document.querySelectorAll(".media-card").length===2');
        }
        await evaluate(`document.querySelector('[data-asset-id="${available.asset_id}"]').closest('.media-card').querySelector('.open-image').click()`);
        await wait('document.querySelector(".viewer-image img")?.naturalWidth===80');
        const pixel = await evaluate(`(() => {
          const img=document.querySelector('.viewer-image img'), canvas=document.createElement('canvas');
          canvas.width=80; canvas.height=40;
          const context=canvas.getContext('2d'); context.drawImage(img,0,0);
          return [...context.getImageData(40,20,1,1).data];
        })()`);
        if (pixel.slice(0,3).some((value,i) => Math.abs(value-[25,100,210][i])>3)) throw new Error("Wrong namesake rendered");
        const preview = await evaluate(`window.photoManager.getPreview(${JSON.stringify(available.asset_id)})`);
        if (!await evaluate(`document.querySelector('.viewer-image img').src===${JSON.stringify("data:image/jpeg;base64,"+preview.base64)}`)) throw new Error("Wrong preview Asset ID");
        await click("Fechar imagem");
        await wait('document.querySelector(".asset-origin")?.textContent.includes("teste/photo (2).png")');
        fullLocation = undefined;
        await click("Localização completa…");
        for (let i=0; i<100 && !fullLocation; i++) await new Promise(resolve => setTimeout(resolve,25));
        if (fullLocation !== png) throw new Error("Wrong complete location");
        console.log(`SUBFOLDER ${view} PASS: correct PNG pixels, Asset ID and complete location; missing parent retained`);
      }

      await click("Calendário");
      await click("20241 foto(s)");
      await click("Fevereiro1 foto(s)");
      await wait('document.querySelectorAll(".calendar-days button").length===29');
      await click("Todos os anos");
      await click("20241 foto(s)");
      await click("Fevereiro1 foto(s)");
      const captureDay = "b.getAttribute('aria-label')==='2024-02-29: 1 foto(s)'";
      await wait(`Array.from(document.querySelectorAll('.calendar-days button')).some(b=>${captureDay})`);
      await evaluate(`Array.from(document.querySelectorAll('.calendar-days button')).find(b=>${captureDay}).click()`);
      await wait(`document.querySelectorAll('.media-card').length===1&&!!document.querySelector('[data-asset-id="${capture.asset_id}"]')`);
      await evaluate('document.querySelector(".card-select").click()');
      await wait('Array.from(document.querySelectorAll(".asset-details dt")).some(dt=>dt.textContent==="Data da captura"&&dt.nextElementSibling.textContent==="2024-02-29 23:30:00")');
      await click("Todos os anos");
      await click(`${mtimeYear}3 foto(s)`);
      await wait('!!document.querySelector(".calendar-months button:not(:disabled)")');
      await evaluate('document.querySelector(".calendar-months button:not(:disabled)").click()');
      const fallbackDay = `b.getAttribute('aria-label')===${JSON.stringify(`${mtimeDay}: 3 foto(s)`)}`;
      await wait(`Array.from(document.querySelectorAll('.calendar-days button')).some(b=>${fallbackDay})`);
      await evaluate(`Array.from(document.querySelectorAll('.calendar-days button')).find(b=>${fallbackDay}).click()`);
      await wait(`document.querySelectorAll('.media-card').length===3&&!!document.querySelector('[data-asset-id="${available.asset_id}"]')&&!document.querySelector('[data-asset-id="${capture.asset_id}"]')&&!document.querySelector('.content').hidden`);
      await evaluate(`document.querySelector('[data-asset-id="${available.asset_id}"]').click()`);
      await wait('Array.from(document.querySelectorAll(".asset-details dt")).some(dt=>dt.textContent==="Data da captura"&&dt.nextElementSibling.textContent==="Não informado")');
      const after = await evaluate('window.photoManager.listGallery({pageSize:24})');
      if (after.items.length!==4 || new Set(after.items.map(i=>i.asset_id)).size!==4
        || after.items.some(i=>i.asset_id===parent.asset_id)) throw new Error("Incorrect live gallery");
      for (const original of originals) {
        if (!readFileSync(original.file).equals(original.bytes) || statSync(original.file).mtimeMs!==original.mtime) throw new Error("Original modified");
      }
      console.log("CALENDAR PASS: UI import; EXIF 2024-02-29 23:30 -03:00; year/month/day/gallery; mtime fallback PNG; originals unchanged");

      // Delete the entire harness-owned subtree without adding anything else.
      rmSync(join(root,"teste"),{recursive:true});
      await wait('document.querySelectorAll(".media-card").length===1&&!document.querySelector(".content").hidden');
      const remaining=await evaluate('window.photoManager.listGallery({pageSize:24})');
      if(remaining.items.length!==1||remaining.items[0].representative_location.relative_path!=="keep.png")throw new Error("Deleted subtree remains in gallery");
      const dates=await evaluate('window.photoManager.getCalendar(null)');
      if(JSON.stringify(dates.buckets)!==JSON.stringify([[mtimeYear,1]])||dates.undated!==0)throw new Error("Deleted subtree remains in calendar counts");
      const removed=updated.items.filter(item=>item.representative_location.relative_path.startsWith("teste/"));
      for(const item of removed){
        const details=await evaluate(`window.photoManager.getAssetDetails(${JSON.stringify(item.asset_id)})`);
        if(details.status!=="ready"||!details.details.locations.every(location=>location.availability==="missing"))throw new Error("Deleted subtree history lost");
      }
      await wait('window.photoManager.getIndexStatus().then(s=>!s.busy&&!s.error)');
      const indexBefore=await evaluate('window.photoManager.getIndexStatus()');
      await evaluate('void(window.__beforeRefreshCard=document.querySelector(".media-card"))');
      await click("Atualizar pastas agora");
      await wait('document.querySelector(".media-card")!==window.__beforeRefreshCard');
      await wait(`window.photoManager.getIndexStatus().then(s=>!s.busy&&!s.error&&s.last_check>${indexBefore.last_check})`);
      const indexAfter=await evaluate('window.photoManager.getIndexStatus()');
      if(indexAfter.revision!==indexBefore.revision)throw new Error("Unchanged scan invented a catalog revision");
      if(await evaluate('document.querySelectorAll(".media-card").length')!==1)throw new Error("Refresh revived deleted cards");
      await click("Pastas");await click("Synthetic");
      await wait('document.querySelectorAll(".media-card").length===1&&document.querySelectorAll(".folder-card").length===0');
      const kept=originals.find(original=>original.file===join(root,"keep.png"));
      if(!readFileSync(kept.file).equals(kept.bytes)||statSync(kept.file).mtimeMs!==kept.mtime)throw new Error("Remaining original modified");
      console.log("DELETED SUBTREE PASS: automatic removal from gallery/calendar/folder navigation; history retained; manual refresh without revision re-queries thumbnails; remaining original unchanged");
      console.log("Native selection and location dialog replaced by synthetic fixtures; native KDE dialogs not tested.");
    } catch (error) {
      console.error(error);
      process.exitCode = 1;
    } finally {
      clearTimeout(watchdog);
      app.quit();
    }
  });
});
await import("../dist/main/main.js");
