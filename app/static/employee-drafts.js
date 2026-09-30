// Survey drafts, including selected photo Blobs, are local to this device and
// partitioned by staff user. They are only uploaded by an explicit sync action.
let connection;
export function openDrafts() {
  if (!connection) connection = new Promise((resolve, reject) => {
    const request = indexedDB.open('tampa-signs-employee-drafts', 1);
    request.onupgradeneeded = () => request.result.createObjectStore('surveys', {keyPath:'local_key'});
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => {connection = null; reject(request.error);};
  });
  return connection;
}
async function operation(mode, apply) {
  const db = await openDrafts();
  return new Promise((resolve, reject) => {
    const transaction = db.transaction('surveys', mode);
    const request = apply(transaction.objectStore('surveys'));
    transaction.oncomplete = () => resolve(request?.result);
    transaction.onerror = () => reject(transaction.error);
    transaction.onabort = () => reject(transaction.error || new Error('Device storage unavailable.'));
  });
}
export const saveDraft = draft => operation('readwrite', store => store.put(draft));
export const getDraft = key => operation('readonly', store => store.get(key));
export const deleteDraft = key => operation('readwrite', store => store.delete(key));
export async function listDrafts(userId) {
  const drafts = await operation('readonly', store => store.getAll());
  return drafts.filter(d => d.user_id === userId).sort((a,b) => b.updated_at.localeCompare(a.updated_at));
}
export async function clearDrafts(userId) {
  const drafts = await listDrafts(userId);
  for (const draft of drafts) await deleteDraft(draft.local_key);
}
