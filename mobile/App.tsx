import { StatusBar } from 'expo-status-bar';
import * as Location from 'expo-location';
import React, { useEffect, useState } from 'react';
import { ActivityIndicator, Linking, ScrollView, StyleSheet, Text, TextInput, TouchableOpacity, View } from 'react-native';

type Role = 'customer' | 'provider';
type Category = { id: number; name: string };
type Profile = { name: string; role: Role; phone: string; phone_verified: boolean; identity_status: string;
  description: string; latitude: number | null; longitude: number | null };
type Offering = { id: number; category: number; category_name: string; pricing: 'fixed' | 'quote';
  price_kes: string | null; active: boolean; profession_verified: boolean };
type NearbyOffering = { id: number; provider_name: string; category_name: string; description: string;
  pricing: 'fixed' | 'quote'; price_kes: string | null; distance_km: number };
type Booking = { id: number; customer_name: string; provider_name: string; category_name: string;
  details: string; address: string; scheduled_for: string; pricing: 'fixed' | 'quote';
  price_kes: string | null; status: string };

const API = (process.env.EXPO_PUBLIC_API_URL || 'http://127.0.0.1:8000/api').replace(/\/$/, '');

async function call<T>(path: string, token: string | null, method = 'GET', body?: object): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API}${path}`, {
      method, headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Token ${token}` } : {}) },
      ...(body ? { body: JSON.stringify(body) } : {}),
    });
  } catch {
    throw new Error('Cannot reach the server. Check your connection and API address.');
  }
  if (response.status === 204) return undefined as T;
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.detail || Object.entries(data).map(([field, value]) => `${field}: ${value}`).join('\n'));
  }
  return data as T;
}

function Button({ title, onPress, secondary = false, disabled = false }: {
  title: string; onPress: () => void; secondary?: boolean; disabled?: boolean;
}) {
  return <TouchableOpacity accessibilityRole="button" disabled={disabled} onPress={onPress}
    style={[styles.button, secondary && styles.secondary, disabled && styles.disabled]}>
    <Text style={[styles.buttonText, secondary && styles.secondaryText]}>{title}</Text>
  </TouchableOpacity>;
}

function Field({ label, value, onChangeText, placeholder, secure = false, multiline = false }: {
  label: string; value: string; onChangeText: (value: string) => void; placeholder?: string;
  secure?: boolean; multiline?: boolean;
}) {
  return <View style={styles.field}><Text style={styles.label}>{label}</Text>
    <TextInput value={value} onChangeText={onChangeText} placeholder={placeholder} placeholderTextColor="#8b9998"
      secureTextEntry={secure} multiline={multiline} autoCapitalize="none"
      style={[styles.input, multiline && styles.multiline]} /></View>;
}

function Choice({ title, selected, onPress }: { title: string; selected: boolean; onPress: () => void }) {
  return <TouchableOpacity accessibilityRole="button" onPress={onPress} style={[styles.chip, selected && styles.chipSelected]}>
    <Text style={[styles.chipText, selected && styles.chipTextSelected]}>{title}</Text>
  </TouchableOpacity>;
}

async function currentLocation() {
  const permission = await Location.requestForegroundPermissionsAsync();
  if (permission.status !== 'granted') throw new Error('Location permission is needed to search or set a service location.');
  const position = await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.Balanced });
  return { latitude: position.coords.latitude, longitude: position.coords.longitude };
}

export default function App() {
  const [token, setToken] = useState<string | null>(null);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [categories, setCategories] = useState<Category[]>([]);
  const [category, setCategory] = useState<number | null>(null);
  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [tab, setTab] = useState<'discover' | 'bookings' | 'account'>('discover');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [firstName, setFirstName] = useState('');
  const [lastName, setLastName] = useState('');
  const [phone, setPhone] = useState('');
  const [role, setRole] = useState<Role>('customer');
  const [code, setCode] = useState('');
  const [description, setDescription] = useState('');
  const [pricing, setPricing] = useState<'fixed' | 'quote'>('quote');
  const [price, setPrice] = useState('');
  const [offerings, setOfferings] = useState<Offering[]>([]);
  const [results, setResults] = useState<NearbyOffering[]>([]);
  const [searched, setSearched] = useState(false);
  const [selected, setSelected] = useState<NearbyOffering | null>(null);
  const [details, setDetails] = useState('');
  const [address, setAddress] = useState('');
  const [when, setWhen] = useState('');
  const [bookings, setBookings] = useState<Booking[]>([]);
  const [quotes, setQuotes] = useState<Record<number, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');

  async function run(action: () => Promise<void>) {
    setError(''); setMessage(''); setBusy(true);
    try { await action(); }
    catch (err) { setError(err instanceof Error ? err.message : 'Something went wrong.'); }
    finally { setBusy(false); }
  }
  async function loadCategories() {
    const data = await call<Category[]>('/categories/', null);
    setCategories(data); setCategory(previous => data.some(item => item.id === previous) ? previous : data[0]?.id ?? null);
  }
  useEffect(() => { void run(loadCategories); }, []);

  async function authenticate() {
    const data = mode === 'login' ? { username, password } : {
      username, password, first_name: firstName, last_name: lastName, phone, role,
    };
    const result = await call<{ token: string; profile: Profile }>(mode === 'login' ? '/login/' : '/register/', null, 'POST', data);
    setToken(result.token); setProfile(result.profile); setDescription(result.profile.description);
    setPassword(''); setTab(result.profile.role === 'provider' ? 'account' : 'discover');
    await loadCategories();
    if (result.profile.role === 'provider') setOfferings(await call<Offering[]>('/offerings/', result.token));
  }
  async function loadAccount() {
    const result = await call<Profile>('/profile/', token);
    setProfile(result); setDescription(result.description);
    if (result.role === 'provider') setOfferings(await call<Offering[]>('/offerings/', token));
  }
  async function loadBookings() { setBookings(await call<Booking[]>('/bookings/', token)); }
  async function search() {
    if (category === null) throw new Error('Choose a service category first.');
    const location = await currentLocation();
    const query = new URLSearchParams({ category: String(category), latitude: String(location.latitude),
      longitude: String(location.longitude), radius: '20' });
    setResults(await call<NearbyOffering[]>(`/nearby/?${query}`, token)); setSearched(true);
  }
  async function book() {
    if (!selected) return;
    if (!/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$/.test(when)) throw new Error('Enter date and time as YYYY-MM-DD HH:MM.');
    const date = new Date(when.replace(' ', 'T'));
    if (Number.isNaN(date.getTime())) throw new Error('Enter a valid date and time.');
    await call('/bookings/', token, 'POST', { offering_id: selected.id, details, address,
      scheduled_for: date.toISOString(), ...(selected.pricing === 'fixed' ? { accepted_fixed_price_kes: selected.price_kes } : {}) });
    setSelected(null); setDetails(''); setAddress(''); setWhen(''); setTab('bookings');
    await loadBookings(); setMessage('Booking request sent.');
  }
  async function action(id: number, name: string) {
    await call(`/bookings/${id}/action/`, token, 'POST', { action: name,
      ...(name === 'quote' ? { price_kes: quotes[id] || '' } : {}) });
    await loadBookings(); setMessage('Booking updated.');
  }

  return <View style={styles.root}><StatusBar style="dark" />
    <ScrollView contentContainerStyle={styles.container} keyboardShouldPersistTaps="handled">
      <View style={styles.hero}><Text style={styles.eyebrow}>NEARBY SERVICES · KENYA</Text>
        <Text style={styles.title}>Find good help nearby.</Text>
        <Text style={styles.subtitle}>Local services, straightforward bookings.</Text></View>
      {busy && <ActivityIndicator color="#087e75" style={styles.loader} />}
      {!!error && <Text accessibilityRole="alert" style={styles.error}>{error}</Text>}
      {!!message && <Text style={styles.notice}>{message}</Text>}
      {!profile || !token ? <View style={styles.card}>
        <Text style={styles.heading}>{mode === 'login' ? 'Welcome back' : 'Create your account'}</Text>
        {mode === 'register' && <>
          <Text style={styles.label}>Account type</Text><View style={styles.row}>
            {(['customer', 'provider'] as const).map(item =>
              <Choice key={item} title={item} selected={item === role} onPress={() => setRole(item)} />)}
          </View>
          <Field label="First name (as on ID)" value={firstName} onChangeText={setFirstName} />
          <Field label="Last name (as on ID)" value={lastName} onChangeText={setLastName} />
          <Field label="Kenyan phone number" value={phone} onChangeText={setPhone} placeholder="+254712345678" />
        </>}
        <Field label="Username" value={username} onChangeText={setUsername} />
        <Field label="Password" value={password} onChangeText={setPassword} secure />
        <Button title={mode === 'login' ? 'Sign in' : 'Create account'} onPress={() => void run(authenticate)} disabled={busy} />
        <Button title={mode === 'login' ? 'Create an account' : 'Already registered? Sign in'} secondary
          onPress={() => { setError(''); setMode(mode === 'login' ? 'register' : 'login'); }} />
      </View> : <>
        <View style={styles.row}>
          {profile.role === 'customer' && <Choice title="Discover" selected={tab === 'discover'} onPress={() => setTab('discover')} />}
          <Choice title="Bookings" selected={tab === 'bookings'} onPress={() => void run(async () => { setTab('bookings'); await loadBookings(); })} />
          <Choice title="Account" selected={tab === 'account'} onPress={() => void run(async () => { setTab('account'); await loadAccount(); })} />
        </View>
        {tab === 'discover' && profile.role === 'customer' && <View style={styles.card}>
          <Text style={styles.heading}>Explore services</Text>
          <Text style={styles.muted}>Find providers within 20 km of your location.</Text>
          <View style={styles.row}>{categories.map(item => <Choice key={item.id} title={item.name} selected={category === item.id}
            onPress={() => { setCategory(item.id); setSelected(null); setResults([]); setSearched(false); }} />)}</View>
          <Button title="Find nearby providers" disabled={busy} onPress={() => void run(search)} />
          {searched && results.length === 0 && <Text style={styles.muted}>No approved providers found nearby.</Text>}
          {results.map(item => <View key={item.id} style={styles.item}>
            <Text style={styles.itemTitle}>{item.provider_name}</Text>
            <Text style={styles.muted}>{item.category_name} · approximately {item.distance_km} km away</Text>
            {!!item.description && <Text style={styles.body}>{item.description}</Text>}
            <Text style={styles.body}>{item.pricing === 'fixed' ? `Fixed price: KSh ${item.price_kes}` : 'Price on request'}</Text>
            <Text style={styles.badge}>Phone, identity and profession checked</Text>
            <Button title="Request a booking" secondary onPress={() => setSelected(item)} />
          </View>)}
          {selected && <View style={styles.item}>
            <Text style={styles.itemTitle}>Book {selected.provider_name}</Text>
            <Text style={styles.muted}>Your details, address and requested time will be shared with the provider.</Text>
            {selected.pricing === 'fixed' && <Text style={styles.body}>By sending, you accept the fixed price of KSh {selected.price_kes}.</Text>}
            <Field label="Describe the job" value={details} onChangeText={setDetails} multiline />
            <Field label="Service address" value={address} onChangeText={setAddress} />
            <Field label="Date and time (your local time)" value={when} onChangeText={setWhen} placeholder="YYYY-MM-DD HH:MM" />
            <Button title="Send booking request" disabled={busy} onPress={() => void run(book)} />
            <Button title="Cancel" secondary onPress={() => setSelected(null)} />
          </View>}
        </View>}
        {tab === 'bookings' && <View style={styles.card}>
          <Text style={styles.heading}>Bookings</Text>
          <Text style={styles.muted}>Payment will be due after you confirm the work is done. M-Pesa is not connected yet.</Text>
          {bookings.length === 0 && <Text style={styles.muted}>No bookings yet.</Text>}
          {bookings.map(item => <View key={item.id} style={styles.item}>
            <Text style={styles.itemTitle}>{item.category_name} · {profile.role === 'customer' ? item.provider_name : item.customer_name}</Text>
            <Text style={styles.badge}>{item.status.replace(/_/g, ' ')}</Text>
            <Text style={styles.body}>{item.details}</Text>
            <Text style={styles.muted}>{item.address} · {new Date(item.scheduled_for).toLocaleString()}</Text>
            {item.price_kes && <Text style={styles.body}>Service price: KSh {item.price_kes}</Text>}
            {profile.role === 'provider' && item.status === 'pending' && item.pricing === 'quote' && <>
              <Field label="Your quote (KSh)" value={quotes[item.id] || ''} onChangeText={value => setQuotes({ ...quotes, [item.id]: value })} />
              <Button title="Send quote" disabled={busy} onPress={() => void run(() => action(item.id, 'quote'))} />
            </>}
            {((profile.role === 'provider' && item.status === 'pending' && item.pricing === 'fixed') ||
              (profile.role === 'customer' && item.status === 'quoted')) &&
              <Button title={profile.role === 'customer' ? 'Accept quote and book' : 'Accept booking'}
                disabled={busy} onPress={() => void run(() => action(item.id, 'accept'))} />}
            {(item.status === 'pending' || item.status === 'quoted') &&
              <Button title="Decline" secondary disabled={busy} onPress={() => void run(() => action(item.id, 'decline'))} />}
            {profile.role === 'provider' && item.status === 'confirmed' &&
              <Button title="Mark job completed" disabled={busy} onPress={() => void run(() => action(item.id, 'complete'))} />}
            {profile.role === 'customer' && item.status === 'completed' && <>
              <Button title="Confirm job completed" disabled={busy} onPress={() => void run(() => action(item.id, 'confirm_completion'))} />
              <Button title="Raise a dispute" secondary disabled={busy} onPress={() => void run(() => action(item.id, 'dispute'))} />
            </>}
            {item.status === 'payment_due' && <Text style={styles.muted}>Payment is due, but online payment is not available in this prototype.</Text>}
            {item.status === 'disputed' && <Text style={styles.muted}>Payment is paused for administrator review.</Text>}
          </View>)}
        </View>}
        {tab === 'account' && <View style={styles.card}>
          <Text style={styles.heading}>Account</Text><Text style={styles.itemTitle}>{profile.name}</Text>
          <Text style={styles.muted}>{profile.role} · {profile.phone}</Text>
          <View style={styles.item}>
            <Text style={styles.itemTitle}>Phone: {profile.phone_verified ? 'verified' : 'not verified'}</Text>
            {!profile.phone_verified && <>
              <Button title="Send verification code" secondary disabled={busy} onPress={() => void run(async () => {
                await call('/verify/phone/start/', token, 'POST'); setMessage('Code requested.');
              })} />
              <Field label="SMS code" value={code} onChangeText={setCode} />
              <Button title="Verify phone" disabled={busy} onPress={() => void run(async () => {
                setProfile(await call<Profile>('/verify/phone/check/', token, 'POST', { code })); setCode('');
              })} />
            </>}
          </View>
          {profile.role === 'provider' && <>
            <View style={styles.item}>
              <Text style={styles.itemTitle}>Identity: {profile.identity_status.replace('_', ' ')}</Text>
              <Text style={styles.muted}>The ID check is handled by Didit. Verification reduces risk but does not guarantee safety.</Text>
              {profile.identity_status !== 'approved' && <>
                <Button title="Start identity check" secondary disabled={busy} onPress={() => void run(async () => {
                  const result = await call<{ url: string }>('/verify/identity/start/', token, 'POST');
                  await Linking.openURL(result.url); await loadAccount();
                })} />
                <Button title="Refresh identity status" secondary disabled={busy} onPress={() => void run(async () => {
                  setProfile(await call<Profile>('/verify/identity/status/', token, 'POST'));
                })} />
              </>}
            </View>
            <View style={styles.item}>
              <Text style={styles.itemTitle}>Service location</Text>
              <Field label="About your services" value={description} onChangeText={setDescription} multiline />
              <Button title="Save description and current location" secondary disabled={busy} onPress={() => void run(async () => {
                const location = await currentLocation();
                setProfile(await call<Profile>('/profile/', token, 'PATCH', { ...location, description }));
                setMessage('Service details saved.');
              })} />
            </View>
            <View style={styles.item}>
              <Text style={styles.itemTitle}>Your services</Text>
              <Text style={styles.muted}>Each service requires a separate qualification review before it appears in search.</Text>
              {offerings.map(item => <View key={item.id} style={styles.offering}>
                <Text style={styles.body}>{item.category_name} · {item.pricing === 'fixed' ? `KSh ${item.price_kes}` : 'Quote'}</Text>
                <Text style={styles.muted}>{item.profession_verified ? 'Profession approved' : 'Awaiting profession review'} · {item.active ? 'Active' : 'Disabled'}</Text>
                <Button title={item.active ? 'Disable service' : 'Enable service'} secondary disabled={busy}
                  onPress={() => void run(async () => {
                    await call(`/offerings/${item.id}/`, token, 'PATCH', { active: !item.active }); await loadAccount();
                  })} />
              </View>)}
              <Text style={styles.label}>Add a service</Text>
              <View style={styles.row}>{categories.map(item => <Choice key={item.id} title={item.name}
                selected={category === item.id} onPress={() => setCategory(item.id)} />)}</View>
              <View style={styles.row}>{(['quote', 'fixed'] as const).map(item =>
                <Choice key={item} title={item === 'fixed' ? 'Fixed price' : 'Quote'} selected={pricing === item} onPress={() => setPricing(item)} />)}</View>
              {pricing === 'fixed' && <Field label="Fixed price (KSh)" value={price} onChangeText={setPrice} />}
              <Button title="Add service" disabled={busy} onPress={() => void run(async () => {
                if (category === null) throw new Error('Choose a service category.');
                await call('/offerings/', token, 'POST', { category, pricing, price_kes: pricing === 'fixed' ? price : null });
                setPrice(''); await loadAccount(); setMessage('Service added; profession review is required.');
              })} />
            </View>
          </>}
          <Button title="Sign out" secondary disabled={busy} onPress={() => void run(async () => {
            await call('/logout/', token, 'POST'); setToken(null); setProfile(null); setBookings([]); setResults([]);
          })} />
        </View>}
      </>}
      <Text style={styles.footer}>Verification is not a guarantee of safety.</Text>
    </ScrollView></View>;
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#f1f7f5' },
  container: { flexGrow: 1, width: '100%', maxWidth: 720, alignSelf: 'center', padding: 22, paddingTop: 64, paddingBottom: 44 },
  hero: { marginBottom: 24 },
  eyebrow: { color: '#087e75', fontWeight: '800', letterSpacing: 1.5, fontSize: 11 },
  title: { color: '#102d36', fontSize: 36, fontWeight: '800', marginTop: 8 },
  subtitle: { color: '#5d7179', fontSize: 16, marginTop: 8, lineHeight: 23 },
  card: { backgroundColor: '#fff', borderRadius: 20, padding: 22, marginBottom: 16, borderWidth: 1, borderColor: '#e0ece8' },
  heading: { color: '#102d36', fontSize: 22, fontWeight: '800', marginBottom: 8 },
  itemTitle: { color: '#173e46', fontWeight: '700', fontSize: 17, marginBottom: 6 },
  muted: { color: '#627781', lineHeight: 21, marginVertical: 6 },
  body: { color: '#173e46', lineHeight: 21, marginVertical: 5 },
  label: { color: '#294b52', fontWeight: '700', fontSize: 13, marginBottom: 7, marginTop: 12 },
  field: { marginBottom: 3 },
  input: { borderWidth: 1, borderColor: '#d8e6e1', borderRadius: 10, padding: 12, color: '#173e46', backgroundColor: '#fbfdfc' },
  multiline: { minHeight: 80, textAlignVertical: 'top' },
  button: { backgroundColor: '#087e75', borderRadius: 10, padding: 13, alignItems: 'center', marginTop: 10, marginRight: 6 },
  secondary: { backgroundColor: '#e8f4f0' },
  disabled: { opacity: 0.5 },
  buttonText: { color: '#fff', fontWeight: '700', textAlign: 'center' },
  secondaryText: { color: '#087e75' },
  row: { flexDirection: 'row', flexWrap: 'wrap', marginVertical: 6 },
  chip: { paddingVertical: 8, paddingHorizontal: 12, borderRadius: 20, backgroundColor: '#e8f4f0', marginRight: 7, marginBottom: 7 },
  chipSelected: { backgroundColor: '#087e75' },
  chipText: { color: '#40645e' },
  chipTextSelected: { color: '#fff', fontWeight: '700' },
  item: { borderTopWidth: 1, borderColor: '#e4eeeb', paddingTop: 16, marginTop: 16 },
  offering: { borderBottomWidth: 1, borderColor: '#e4eeeb', paddingBottom: 12 },
  badge: { color: '#087e75', fontWeight: '700', fontSize: 12, marginTop: 5, textTransform: 'capitalize' },
  error: { color: '#8a2929', backgroundColor: '#fdecec', padding: 14, borderRadius: 10, marginBottom: 12 },
  notice: { color: '#155e54', backgroundColor: '#dbf3e8', padding: 14, borderRadius: 10, marginBottom: 12 },
  loader: { marginBottom: 12 },
  footer: { color: '#788f91', fontSize: 12, textAlign: 'center', marginTop: 10 },
});
