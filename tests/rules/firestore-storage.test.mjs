import { after, before, test } from 'node:test';
import { readFileSync } from 'node:fs';
import { initializeTestEnvironment, assertFails, assertSucceeds } from '@firebase/rules-unit-testing';
import { doc, getDoc, setDoc, updateDoc, serverTimestamp, collection, getDocs, query, where } from 'firebase/firestore';
import { ref, uploadBytes, getBytes } from 'firebase/storage';

let env;
const projectId = 'demo-relay-rules';
const firestorePort = Number(process.env.RULES_FIRESTORE_PORT || 8095);
if (!Number.isInteger(firestorePort) || firestorePort < 1024 || firestorePort > 65535) {
  throw new Error('Invalid isolated rules emulator port');
}
const victim = () => env.authenticatedContext('victim-a', { firebase: { sign_in_provider: 'anonymous' } });
const other = () => env.authenticatedContext('victim-b', { role: 'victim' });
const receiver = () => env.authenticatedContext('receiver-a', { role: 'receiver', orgId: 'bank-a' });
const reviewer = () => env.authenticatedContext('reviewer-a', { role: 'reviewer', orgId: 'review-a' });
const accessExpiresAtMs = Date.now() + 86_400_000;

before(async () => {
  env = await initializeTestEnvironment({
    projectId,
    firestore: { host: '127.0.0.1', port: firestorePort, rules: readFileSync('infra/firestore.rules', 'utf8') },
    storage: { host: '127.0.0.1', port: 9299, rules: readFileSync('infra/storage.rules', 'utf8') },
  });
  await env.withSecurityRulesDisabled(async ctx => {
    const db = ctx.firestore();
    const records = {
      'cases/case-a': { victimUid: 'victim-a', facts: { amount: 123 }, status: 'INTAKE', accessExpiresAtMs },
      'cases/case-b': { victimUid: 'victim-b', facts: { amount: 456 }, status: 'INTAKE', accessExpiresAtMs },
      'cases/expired': { victimUid: 'victim-a', accessExpiresAtMs: Date.now() - 60_000 },
      'cases/deleting': { victimUid: 'victim-a', accessExpiresAtMs, deleting: true },
      'cases/deleted': { victimUid: 'victim-a', accessExpiresAtMs, deleted: true },
      'cases/legacy': { victimUid: 'victim-a' },
      'cases/string-expiry': { victimUid: 'victim-a', accessExpiresAtMs: String(accessExpiresAtMs) },
      'cases/case-a/events/event-a': { action: 'case.created' },
      'cases/case-a/packets/packet-a': { recipientOrgId: 'bank-a', status: 'SENT' },
      'receiverViews/bank-a/cases/case-a': { caseRef: 'SYN-A', summary: 'Sanitized', accessExpiresAtMs },
      'receiverViews/bank-b/cases/case-a': { caseRef: 'SYN-A', summary: 'Other institution', accessExpiresAtMs },
      'receiverViews/bank-a/cases/expired': { caseRef: 'SYN-X', accessExpiresAtMs: Date.now() - 60_000 },
      'receiverViews/bank-a/cases/expired/packets/p1': { synthetic: true },
      'receiverPrivate/bank-a/cases/case-a/packets/packet-a': { ownerUid: 'victim-a' },
      'receiverViews/bank-a/cases/case-a/packets/packet-a': { content: 'Addressed only' },
      'notifications/notification-a': { uid: 'victim-a', readAt: null, textKey: 'planReady' },
      'notifications/notification-b': { uid: 'victim-b', readAt: null },
      'sources/source-a': { orgId: 'review-a', title: 'Synthetic source' },
      'sources/source-a/passages/p1': { text: 'Synthetic passage' },
      'sources/source-b': { orgId: 'review-b', title: 'Other source' },
      'packs/pack-a/versions/1': { orgId: 'review-a', status: 'draft', reviewNotes: 'Private' },
      'packs/pack-b/versions/1': { orgId: 'review-b', status: 'draft' },
      'publishedPacks/pack-a': { status: 'published', name: 'Synthetic public pack' },
      'publishedPacks/draft-a': { status: 'draft' },
      'jobs/job-a': { victimUid: 'victim-a', state: 'queued' },
      'idempotency/key-a': { response: 'Private' },
    };
    for (const caseId of ['case-a', 'expired', 'deleting', 'deleted', 'legacy', 'string-expiry']) {
      for (const child of ['evidence/e1', 'transcript/t1', 'packets/p1', 'events/e1', 'pipeline/p1', 'plans/p1',
        'packets/p1/versions/1', 'plans/p1/versions/1']) {
        records[`cases/${caseId}/${child}`] = { synthetic: true };
      }
    }
    await Promise.all(Object.entries(records).map(([path, value]) => setDoc(doc(db, path), value)));
    await uploadBytes(ref(ctx.storage(), 'evidence/victim-a/case-a/synthetic.txt'), new TextEncoder().encode('Synthetic only'));
    await uploadBytes(ref(ctx.storage(), 'sources/review-a/source-a/source.txt'), new TextEncoder().encode('Synthetic source'));
  });
});
after(async () => { if (env) await env.cleanup(); });

const canRead = (context, path) => getDoc(doc(context.firestore(), path));

test('anonymous Firebase victim owns case', async () => assertSucceeds(canRead(victim(), 'cases/case-a')));
test('active owner can read all allowed child collections and version history', async () => {
  for (const child of ['evidence/e1', 'transcript/t1', 'packets/p1', 'events/e1', 'pipeline/p1', 'plans/p1',
    'packets/p1/versions/1', 'plans/p1/versions/1']) {
    await assertSucceeds(canRead(victim(), `cases/case-a/${child}`));
  }
});
for (const caseId of ['expired', 'deleting', 'deleted', 'legacy', 'string-expiry']) {
  test(`${caseId} case is denied even to its authenticated owner`, async () => {
    await assertFails(canRead(victim(), `cases/${caseId}`));
  });
  test(`${caseId} parent blocks all allowed children and immutable history`, async () => {
    for (const child of ['evidence/e1', 'transcript/t1', 'packets/p1', 'events/e1', 'pipeline/p1', 'plans/p1',
      'packets/p1/versions/1', 'plans/p1/versions/1']) {
      await assertFails(canRead(victim(), `cases/${caseId}/${child}`));
    }
  });
}
test('victim cannot read another case', async () => assertFails(canRead(victim(), 'cases/case-b')));
test('unauthenticated cannot read case', async () => assertFails(canRead(env.unauthenticatedContext(), 'cases/case-a')));
test('receiver addressed packet does not expose raw case', async () => assertFails(canRead(receiver(), 'cases/case-a')));
test('receiver cannot read raw packet subcollection', async () => assertFails(canRead(receiver(), 'cases/case-a/packets/packet-a')));
test('receiver own sanitized projection allowed', async () => assertSucceeds(canRead(receiver(), 'receiverViews/bank-a/cases/case-a')));
test('receiver other org denied', async () => assertFails(canRead(receiver(), 'receiverViews/bank-b/cases/case-a')));
test('receiver own sanitized packet allowed', async () => assertSucceeds(canRead(receiver(), 'receiverViews/bank-a/cases/case-a/packets/packet-a')));
test('receiver expired projection denied', async () => assertFails(canRead(receiver(), 'receiverViews/bank-a/cases/expired')));
test('receiver expired child denied', async () => assertFails(canRead(receiver(), 'receiverViews/bank-a/cases/expired/packets/p1')));
test('receiver private delivery ledger denied', async () => assertFails(canRead(receiver(), 'receiverPrivate/bank-a/cases/case-a/packets/packet-a')));
test('victim cannot read receiver projection', async () => assertFails(canRead(victim(), 'receiverViews/bank-a/cases/case-a')));
test('role alone without organization denied', async () => assertFails(canRead(env.authenticatedContext('r', { role: 'receiver' }), 'receiverViews/bank-a/cases/case-a')));
test('client cannot create case', async () => assertFails(setDoc(doc(victim().firestore(), 'cases/new-case'), { victimUid: 'victim-a' })));
test('client cannot mutate authoritative facts', async () => assertFails(updateDoc(doc(victim().firestore(), 'cases/case-a'), { facts: { amount: 999 } })));
test('client cannot forge audit', async () => assertFails(setDoc(doc(victim().firestore(), 'cases/case-a/events/fake'), { action: 'packet.approved' })));
test('receiver cannot mutate decision projection', async () => assertFails(updateDoc(doc(receiver().firestore(), 'receiverViews/bank-a/cases/case-a'), { decision: 'hold' })));
test('owner reads audit', async () => assertSucceeds(canRead(victim(), 'cases/case-a/events/event-a')));
test('owner reads notifications', async () => assertSucceeds(canRead(victim(), 'notifications/notification-a')));
test('other notifications denied', async () => assertFails(canRead(other(), 'notifications/notification-a')));
test('owner marks notification read only', async () => assertSucceeds(updateDoc(doc(victim().firestore(), 'notifications/notification-a'), { readAt: serverTimestamp() })));
test('notification ownership cannot be rewritten', async () => assertFails(updateDoc(doc(victim().firestore(), 'notifications/notification-a'), { uid: 'victim-b', readAt: serverTimestamp() })));
test('notification content cannot be rewritten', async () => assertFails(updateDoc(doc(victim().firestore(), 'notifications/notification-a'), { textKey: 'forged', readAt: serverTimestamp() })));
test('scoped notification query allowed', async () => assertSucceeds(getDocs(query(collection(victim().firestore(), 'notifications'), where('uid', '==', 'victim-a')))));
test('broad notification query denied', async () => assertFails(getDocs(collection(victim().firestore(), 'notifications'))));
test('reviewer own source allowed', async () => assertSucceeds(canRead(reviewer(), 'sources/source-a')));
test('reviewer own passage allowed', async () => assertSucceeds(canRead(reviewer(), 'sources/source-a/passages/p1')));
test('reviewer other org source denied', async () => assertFails(canRead(reviewer(), 'sources/source-b')));
test('reviewer own draft allowed', async () => assertSucceeds(canRead(reviewer(), 'packs/pack-a/versions/1')));
test('reviewer other org draft denied', async () => assertFails(canRead(reviewer(), 'packs/pack-b/versions/1')));
test('reviewer source writes go through API', async () => assertFails(updateDoc(doc(reviewer().firestore(), 'sources/source-a'), { title: 'Forged' })));
test('reviewer publish through API only', async () => assertFails(updateDoc(doc(reviewer().firestore(), 'packs/pack-a/versions/1'), { status: 'published' })));
test('public published projection allowed', async () => assertSucceeds(canRead(env.unauthenticatedContext(), 'publishedPacks/pack-a')));
test('public unpublished projection denied', async () => assertFails(canRead(env.unauthenticatedContext(), 'publishedPacks/draft-a')));
test('public private pack denied', async () => assertFails(canRead(env.unauthenticatedContext(), 'packs/pack-a/versions/1')));
test('job owner allowed', async () => assertSucceeds(canRead(victim(), 'jobs/job-a')));
test('job other owner denied', async () => assertFails(canRead(other(), 'jobs/job-a')));
test('idempotency data never client-readable', async () => assertFails(canRead(victim(), 'idempotency/key-a')));
test('storage owner evidence read allowed', async () => assertSucceeds(getBytes(ref(victim().storage(), 'evidence/victim-a/case-a/synthetic.txt'))));
test('storage other victim denied', async () => assertFails(getBytes(ref(other().storage(), 'evidence/victim-a/case-a/synthetic.txt'))));
test('storage receiver raw evidence denied', async () => assertFails(getBytes(ref(receiver().storage(), 'evidence/victim-a/case-a/synthetic.txt'))));
test('storage owner uploads require API signed URL', async () => assertFails(uploadBytes(ref(victim().storage(), 'evidence/victim-a/case-a/new.txt'), new Uint8Array([1]))));
test('storage reviewer own source allowed', async () => assertSucceeds(getBytes(ref(reviewer().storage(), 'sources/review-a/source-a/source.txt'))));
test('storage reviewer other org denied', async () => assertFails(getBytes(ref(env.authenticatedContext('other-reviewer', { role: 'reviewer', orgId: 'review-b' }).storage(), 'sources/review-a/source-a/source.txt'))));

