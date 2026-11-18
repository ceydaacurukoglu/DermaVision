import React, { useEffect, useRef, useState } from 'react';
import { Text, View } from 'react-native';
import * as WebBrowser from 'expo-web-browser';
import * as Linking from 'expo-linking';
import Constants from 'expo-constants';
import DateTimePicker from '@react-native-community/datetimepicker';
import { Ionicons } from '@expo/vector-icons';
import { BASE_URL, api, isimRe, mailRe, pwErr, setToken } from '../api';
import { Brand, Btn, Check, Choice, ErrText, Field, H1, Link, Logo, Note, Screen, Sub, useTheme } from '../ui';

WebBrowser.maybeCompleteAuthSession();

const NEDEN = {
  iptal: 'Google girişi iptal edildi ya da izin verilmedi.',
  durum: 'Güvenlik doğrulaması eşleşmedi.',
  anahtar: 'Sunucuda GOOGLE_CLIENT_SECRET tanımlı değil.',
  jeton: 'Google, giriş kodunu doğrulamadı (secret yanlış olabilir).',
  eposta: 'Google hesabınızın e-postası doğrulanmamış.',
};

/* ------------------------------------------------------------ Karşılama */
export function Welcome({ onStart }) {
  const c = useTheme();
  const halka = (s, bg, border) => ({ position: 'absolute', width: s, height: s, borderRadius: s / 2, backgroundColor: bg, borderWidth: border ? 1 : 0, borderColor: c.line });
  const chip = (txt, icon, pos) => (
    <View style={[{ position: 'absolute', flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: c.card, borderWidth: 1, borderColor: c.line, borderRadius: 999, paddingVertical: 5, paddingHorizontal: 11 }, pos]}>
      <Ionicons name={icon} size={14} color={c.blue} />
      <Text style={{ fontSize: 11.5, fontWeight: '500', color: c.ink }}>{txt}</Text>
    </View>
  );
  return (
    <Screen>
      <View style={{ alignItems: 'center', paddingTop: 4 }}>
        <Text style={{ color: c.blue, fontSize: 11, fontWeight: '600', letterSpacing: 0.6, marginBottom: 6 }}>CİLT SAĞLIĞI İÇİN BİR İLK ADIM</Text>
        <View style={{ width: 250, height: 250, marginVertical: 14, alignItems: 'center', justifyContent: 'center' }}>
          <View style={halka(250, 'transparent', true)} />
          <View style={halka(196, c.blue + '1A')} />
          <View style={halka(146, c.blue + '29')} />
          <View style={{ width: 104, height: 104, borderRadius: 26, backgroundColor: c.card, alignItems: 'center', justifyContent: 'center', elevation: 6, shadowColor: c.navy, shadowOpacity: 0.25, shadowRadius: 14, shadowOffset: { width: 0, height: 6 } }}>
            <Logo size={72} />
          </View>
          {chip('Fark et', 'scan-outline', { left: -4, top: 36 })}
          {chip('Anla', 'sparkles-outline', { right: -2, bottom: 46 })}
        </View>
        <Text style={{ fontSize: 34, color: c.navy, fontWeight: '700', letterSpacing: -0.5 }}>DermaVision</Text>
        <Text style={{ color: c.blue, fontSize: 11, letterSpacing: 0.6, marginTop: 2, marginBottom: 18 }}>AI DERMATOLOGY</Text>
        <Text style={{ fontSize: 21, lineHeight: 26, fontWeight: '700', color: c.ink, textAlign: 'center', marginBottom: 10 }}>Cildinizi tanıyın.{'\n'}Bir adım önde olun.</Text>
        <Sub style={{ textAlign: 'center' }}>Yapay zeka destekli ön değerlendirme ile cildinizdeki değişimleri anlamaya başlayın.</Sub>
        <Btn title="Başlayalım" iconRight="arrow-forward" onPress={onStart} style={{ alignSelf: 'stretch' }} />
        <Note style={{ marginTop: 16 }}>Bir tanı aracı değildir.{'\n'}Dermatolog muayenesinin yerini tutmaz.</Note>
      </View>
    </Screen>
  );
}

/* ------------------------------------------------------------ Giriş */
export function Login({ go, toast, onLogin }) {
  const [em, setEm] = useState('');
  const [pw, setPw] = useState('');
  const [rem, setRem] = useState(false);
  const [e1, setE1] = useState('');
  const [e2, setE2] = useState('');
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    const mail = em.trim();
    const a = !mail ? 'E-posta adresinizi girin.' : !mailRe.test(mail) ? 'Geçerli bir e-posta girin (örneğin ad@ornek.com).' : '';
    const b = !pw ? 'Şifrenizi girin.' : '';
    setE1(a);
    setE2(b);
    if (a || b) return;
    setBusy(true);
    try {
      const d = await api('/api/giris', { method: 'POST', body: { eposta: mail, sifre: pw, beni_hatirla: rem } });
      await setToken(d.token, rem);
      setPw('');
      onLogin();
    } catch (x) {
      setE2(x.message);
    } finally {
      setBusy(false);
    }
  };

  const bitti = useRef(false);

  const donusIsle = async (url) => {
    if (bitti.current) return;
    const q = Linking.parse(url).queryParams || {};
    if (q.token) {
      bitti.current = true;
      await setToken(String(q.token), true);
      onLogin();
    } else if (q.neden) {
      bitti.current = true;
      toast('Google ile giriş başarısız: ' + (NEDEN[q.neden] || q.neden), 8000);
    }
  };

  useEffect(() => {
    const sub = Linking.addEventListener('url', ({ url }) => {
      if (url.includes('giris')) donusIsle(url);
    });
    return () => sub.remove();
  }, []);

  const google = async () => {
    console.log('[Google] düğmeye basıldı');
    bitti.current = false;
    toast('Google açılıyor…', 2500);
    // Expo Go yalnızca exp:// adreslerini tanır. Expo'nun verdiği sunucu adresinden dönüş adresini kendimiz kuruyoruz.
    const host = Constants.expoConfig?.hostUri || Constants.expoGoConfig?.debuggerHost;
    const donus = host ? `exp://${host}/--/giris` : Linking.createURL('giris');
    console.log('[Google] hostUri:', host, '| ortam:', Constants.executionEnvironment);
    console.log('[Google] dönüş adresi:', donus);
    const adres = `${BASE_URL}/api/auth/google?donus=${encodeURIComponent(donus)}`;
    console.log('[Google] açılacak adres:', adres);
    try {
      const r = await WebBrowser.openAuthSessionAsync(adres, donus);
      console.log('[Google] sonuç:', JSON.stringify(r));
      if (r.type === 'success') await donusIsle(r.url);
      else if (r.type !== 'dismiss') toast('Google girişi tamamlanmadı (' + r.type + ').');
    } catch (e) {
      toast('Google açılamadı: ' + (e?.message || e), 8000);
    }
  };

  return (
    <Screen>
      <Brand />
      <H1>İyi ki geldiniz.</H1>
      <Sub>Cilt sağlığınıza ayrıntılı bakmak için küçük bir adımda yanınızdayız. Hesabınıza giriş yapın.</Sub>

      <Field label="E-posta adresi" icon="mail-outline" value={em} onChangeText={(t) => { setEm(t); setE1(''); }} error={e1} placeholder="deniz.yilmaz@ornek.com" keyboardType="email-address" autoComplete="email" />
      <Field label="Şifre" icon="lock-closed-outline" secure value={pw} onChangeText={(t) => { setPw(t); setE2(''); }} error={e2} placeholder="••••••••" autoComplete="current-password" onSubmitEditing={submit} />

      <View style={{ flexDirection: 'row', alignItems: 'center', marginBottom: 4 }}>
        <Check checked={rem} onChange={setRem} style={{ marginBottom: 0, flex: 1 }}>Beni hatırla</Check>
        <View style={{ flexShrink: 0, marginLeft: 12 }}>
          <Link onPress={() => go('forgot')}>Şifremi unuttum</Link>
        </View>
      </View>
      <View style={{ height: 12 }} />
      <Btn title="Giriş yap" iconRight="arrow-forward" onPress={submit} loading={busy} />

      <View style={{ flexDirection: 'row', justifyContent: 'center', gap: 4, marginTop: 16 }}>
        <Text style={{ fontSize: 13, color: '#8895AD' }}>Henüz hesabınız yok mu?</Text>
        <Link onPress={() => go('signup')}>Kayıt olun</Link>
      </View>

      <Sep />
      <Btn variant="o" title="Google ile giriş yap" icon="logo-google" onPress={google} />
      <Note style={{ marginTop: 32 }}>Mahremiyetiniz önceliğimiz.{'\n'}Gizlilik Politikası · Kullanım Koşulları</Note>
    </Screen>
  );
}

function Sep() {
  const c = useTheme();
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12, marginVertical: 18 }}>
      <View style={{ flex: 1, height: 1, backgroundColor: c.line }} />
      <Text style={{ color: c.mute, fontSize: 13 }}>veya</Text>
      <View style={{ flex: 1, height: 1, backgroundColor: c.line }} />
    </View>
  );
}

/* ------------------------------------------------------------ Şifremi unuttum */
export function Forgot({ go, toast }) {
  const c = useTheme();
  const [em, setEm] = useState('');
  const [err, setErr] = useState('');
  const [busy, setBusy] = useState(false);
  const send = async () => {
    if (!mailRe.test(em.trim())) { setErr('Geçerli bir e-posta girin.'); return; }
    setErr('');
    setBusy(true);
    try {
      const d = await api('/api/sifre-unuttum', { method: 'POST', body: { eposta: em.trim() } });
      toast(d.mesaj, 6000);
      go('login');
    } catch (x) {
      setErr(x.message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Screen>
      <Brand />
      <H1>Şifremi unuttum</H1>
      <Sub>Hesabınıza kayıtlı e-posta adresini girin. Şifrenizi yenilemeniz için size bir bağlantı gönderelim.</Sub>
      <Field label="E-posta adresi" icon="mail-outline" value={em} onChangeText={setEm} placeholder="ornek@eposta.com" keyboardType="email-address" autoComplete="email" error={err} />
      <Btn title="Sıfırlama bağlantısı gönder" onPress={send} loading={busy} />
      <View style={{ alignItems: 'center', marginTop: 24 }}>
        <Link onPress={() => go('login')} style={{ fontSize: 13.5 }}>← Giriş yap ekranına dön</Link>
      </View>

      <View style={{ flexDirection: 'row', gap: 12, alignItems: 'flex-start', backgroundColor: c.tint, borderRadius: 12, padding: 14, marginTop: 28 }}>
        <Ionicons name="mail-outline" size={20} color={c.blue} style={{ marginTop: 1 }} />
        <Text style={{ flex: 1, fontSize: 12.5, lineHeight: 19, color: c.mute }}>
          E-postayı bulamazsanız spam / gereksiz klasörünü kontrol edin. Güvenliğiniz için şifrenizi kimseyle paylaşmayın.
        </Text>
      </View>

      <View style={{ alignItems: 'center', marginTop: 36 }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
          <Ionicons name="checkmark-circle-outline" size={16} color={c.blue} />
          <Text style={{ fontSize: 13, fontWeight: '600', color: c.blue }}>Gizliliğiniz bizim önceliğimiz</Text>
        </View>
        <Text style={{ fontSize: 11.5, color: c.mute, marginTop: 4, textAlign: 'center' }}>Cilt sağlığınız ve gizliliğiniz bizim için önemli.</Text>
      </View>
    </Screen>
  );
}

/* ------------------------------------------------------------ Kayıt */
const tarihStr = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;

export function Signup({ go, toast }) {
  const c = useTheme();
  const [ad, setAd] = useState('');
  const [soyad, setSoyad] = useState('');
  const [em, setEm] = useState('');
  const [p, setP] = useState('');
  const [p2, setP2] = useState('');
  const [dob, setDob] = useState(null);
  const [dobAtla, setDobAtla] = useState(false);
  const [showPick, setShowPick] = useState(false);
  const [g, setG] = useState(null);
  const [adult, setAdult] = useState(false);
  const [kvkk, setKvkk] = useState(false);
  const [terms, setTerms] = useState(false);
  const [err, setErr] = useState('');
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    const a = ad.trim().replace(/\s+/g, ' ');
    const s = soyad.trim().replace(/\s+/g, ' ');
    const e =
      !isimRe.test(a) ? 'Adınızı girin; rakam veya özel karakter içermemeli.'
      : !isimRe.test(s) ? 'Soyadınızı girin; rakam veya özel karakter içermemeli.'
      : !mailRe.test(em.trim()) ? 'Geçerli bir e-posta girin.'
      : pwErr(p) || (p !== p2 ? 'Şifreler eşleşmiyor.' : '')
      || (!dob && !dobAtla ? 'Doğum tarihinizi girin ya da "Belirtmek istemiyorum"u seçin.' : '')
      || (!(adult && kvkk && terms) ? 'Zorunlu onay kutularını işaretleyin.' : '');
    setErr(e);
    if (e) return;
    setBusy(true);
    try {
      const d = await api('/api/kayit', {
        method: 'POST',
        body: { ad: a, soyad: s, eposta: em.trim(), sifre: p, sifre_tekrar: p2, dogum_tarihi: dobAtla ? null : tarihStr(dob), cinsiyet: g, yetiskin_onay: true, kvkk_onay: true, kosul_onay: true },
      });
      toast(d.mesaj, 8000);
      go('login');
    } catch (x) {
      setErr(x.message);
    } finally {
      setBusy(false);
    }
  };

  const h2 = (t, mt = 0) => <Text style={{ fontSize: 15, fontWeight: '700', color: c.ink, marginTop: mt, marginBottom: 12 }}>{t}</Text>;

  return (
    <Screen>
      <Brand />
      <H1>Hesap oluşturun.</H1>
      <Sub>Sizi tanıyalım. Bilgilerinizi ekleyerek cilt sağlığınız için ilk adımı atın.</Sub>

      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-end' }}>
        {h2('Hesap bilgileri')}
        <Text style={{ fontSize: 11, color: c.mute, marginBottom: 12 }}>* Zorunlu alan</Text>
      </View>
      <View style={{ flexDirection: 'row', gap: 10 }}>
        <View style={{ flex: 1 }}><Field label="Ad *" value={ad} onChangeText={setAd} placeholder="Deniz" autoCapitalize="words" autoComplete="given-name" /></View>
        <View style={{ flex: 1 }}><Field label="Soyad *" value={soyad} onChangeText={setSoyad} placeholder="Yılmaz" autoCapitalize="words" autoComplete="family-name" /></View>
      </View>
      <Field label="E-posta *" icon="mail-outline" value={em} onChangeText={setEm} placeholder="deniz.yilmaz@ornek.com" keyboardType="email-address" autoComplete="email" />
      <Field label="Şifre *" icon="lock-closed-outline" secure value={p} onChangeText={setP} placeholder="••••••••" autoComplete="new-password" />
      <Text style={{ fontSize: 11, color: c.mute, marginTop: -8, marginBottom: 14 }}>En az 8 karakter; büyük harf, küçük harf ve rakam içermeli.</Text>
      <Field label="Şifre tekrarı *" icon="lock-closed-outline" secure value={p2} onChangeText={setP2} placeholder="••••••••" autoComplete="new-password" />

      {h2('Kişisel bilgiler', 10)}
      <Text style={{ fontSize: 13, fontWeight: '600', color: c.ink, marginBottom: 6 }}>Doğum tarihi</Text>
      <Btn
        variant="o"
        title={dob ? tarihStr(dob) : 'Tarih seçin'}
        icon="calendar-outline"
        disabled={dobAtla}
        onPress={() => setShowPick(true)}
        style={{ justifyContent: 'flex-start', paddingHorizontal: 14, height: 48, marginBottom: 10 }}
      />
      {showPick ? (
        <DateTimePicker
          value={dob || new Date(2000, 0, 1)}
          mode="date"
          maximumDate={new Date()}
          onChange={(ev, d) => { setShowPick(false); if (ev.type === 'set' && d) setDob(d); }}
        />
      ) : null}
      <Check checked={dobAtla} onChange={(v) => { setDobAtla(v); if (v) setDob(null); }}>Belirtmek istemiyorum</Check>

      <Text style={{ fontSize: 13, fontWeight: '600', color: c.ink, marginBottom: 6 }}>Cinsiyet</Text>
      <View style={{ flexDirection: 'row', gap: 10, marginBottom: 10 }}>
        <Choice style={{ flex: 1 }} label="Kadın" selected={g === 'kadin'} onPress={() => setG('kadin')} />
        <Choice style={{ flex: 1 }} label="Erkek" selected={g === 'erkek'} onPress={() => setG('erkek')} />
      </View>
      <Choice style={{ marginBottom: 24 }} label="Belirtmek istemiyorum" selected={g === 'diger'} onPress={() => setG('diger')} />

      <Check checked={adult} onChange={setAdult}>18 yaşından büyük olduğumu beyan ederim. *</Check>
      <Check checked={kvkk} onChange={setKvkk}>KVKK Aydınlatma Metni'ni ve Gizlilik Politikası'nı okudum. *</Check>
      <Check checked={terms} onChange={setTerms}>Kullanım Koşulları'nı okudum ve kabul ediyorum. *</Check>

      <ErrText style={{ textAlign: 'center' }}>{err}</ErrText>
      <Btn title="Hesap oluştur" onPress={submit} loading={busy} />
      <View style={{ flexDirection: 'row', justifyContent: 'center', gap: 4, marginTop: 20 }}>
        <Text style={{ fontSize: 13, color: c.mute }}>Zaten hesabınız var mı?</Text>
        <Link onPress={() => go('login')}>Giriş yapın</Link>
      </View>
    </Screen>
  );
}
