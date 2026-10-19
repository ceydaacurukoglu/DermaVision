import React, { useState } from 'react';
import { Image, Text, TextInput, View } from 'react-native';
import * as ImagePicker from 'expo-image-picker';
import { Ionicons } from '@expo/vector-icons';
import { api } from '../api';
import { Brand, Btn, Check, ErrText, H1, Link, Note, Screen, Sub, useTheme } from '../ui';

const MAX = 10 * 1024 * 1024;

export function Upload({ onLogout, onDone, onExpired }) {
  const c = useTheme();
  const [asset, setAsset] = useState(null);
  const [consent, setConsent] = useState(false);
  const [info, setInfo] = useState('');
  const [err, setErr] = useState('');
  const [busy, setBusy] = useState(false);

  const sec = async (kaynak) => {
    setErr('');
    let r;
    try {
      if (kaynak === 'kamera') {
        const izin = await ImagePicker.requestCameraPermissionsAsync();
        if (!izin.granted) { setErr('Kamera izni verilmedi. Ayarlardan izin verin ya da Galeri ile fotoğraf seçin.'); return; }
        r = await ImagePicker.launchCameraAsync({ mediaTypes: ['images'], quality: 0.7, base64: true });
      } else {
        r = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ['images'], quality: 0.7, base64: true });
      }
    } catch (e) {
      setErr('Fotoğraf seçilemedi.');
      return;
    }
    if (r.canceled) return;
    const a = r.assets[0];
    const mime = a.mimeType || 'image/jpeg';
    if (!/^image\/(jpeg|png)$/.test(mime)) { setErr('Lütfen JPG veya PNG biçiminde bir fotoğraf seçin.'); return; }
    if (a.fileSize && a.fileSize > MAX) { setErr('Dosya 10 MB sınırını aşıyor. Daha küçük bir fotoğraf seçin.'); return; }
    setAsset({ ...a, mimeType: mime, kaynak: kaynak === 'kamera' ? 'kamera' : 'galeri' });
  };

  const gonder = async () => {
    setBusy(true);
    setErr('');
    if (!asset.base64) {
      setBusy(false);
      setErr('Fotoğraf okunamadı. Lütfen fotoğrafı yeniden seçin.');
      return;
    }
    try {
      await api('/api/gorseller/json', {
        method: 'POST',
        body: { dosya_base64: asset.base64, mime: asset.mimeType, onay: true, bilgi: info, gorsel_kaynak: asset.kaynak || 'galeri' },
      });
      onDone(asset);
    } catch (x) {
      if (x.status === 401) onExpired();
      else setErr(x.message || 'Yükleme başarısız oldu. Tekrar deneyin.');
    } finally {
      setBusy(false);
    }
  };

  const tip = (icon, b, s) => (
    <View style={{ flexDirection: 'row', gap: 12, alignItems: 'flex-start', marginBottom: 10 }}>
      <Ionicons name={icon} size={20} color={c.blue} style={{ marginTop: 2 }} />
      <View style={{ flex: 1 }}>
        <Text style={{ fontSize: 13, fontWeight: '600', color: c.ink }}>{b}</Text>
        <Text style={{ fontSize: 13, color: c.mute }}>{s}</Text>
      </View>
    </View>
  );
  const kart = { backgroundColor: c.card, borderWidth: 1, borderColor: c.line, borderRadius: 14, padding: 16, marginBottom: 16 };

  return (
    <Screen menu>
      <Brand right={<Link onPress={onLogout}>Çıkış yap</Link>} />
      <Text style={{ color: c.blue, fontSize: 11, fontWeight: '700', letterSpacing: 0.5, marginBottom: 4 }}>FOTOĞRAF İLE ÖN DEĞERLENDİRME</Text>
      <H1>Cildinize birlikte bakalım</H1>
      <Sub>İncelemek istediğiniz cilt bölgesinin net bir fotoğrafını ekleyin.</Sub>

      <View style={{ borderWidth: 1.5, borderStyle: asset ? 'solid' : 'dashed', borderColor: c.blue, backgroundColor: c.tint, borderRadius: 16, minHeight: 170, alignItems: 'center', justifyContent: 'center', padding: asset ? 10 : 18, marginBottom: 12, overflow: 'hidden' }}>
        {asset ? (
          <Image source={{ uri: asset.uri }} style={{ width: '100%', height: 280, borderRadius: 10 }} resizeMode="cover" accessibilityLabel="Seçilen cilt fotoğrafı" />
        ) : (
          <>
            <View style={{ width: 44, height: 44, borderRadius: 12, backgroundColor: c.card, alignItems: 'center', justifyContent: 'center', marginBottom: 6 }}>
              <Ionicons name="scan-outline" size={22} color={c.blue} />
            </View>
            <Text style={{ fontSize: 15, fontWeight: '700', color: c.ink }}>Bir cilt fotoğrafı ekleyin</Text>
            <Text style={{ fontSize: 12.5, color: c.mute }}>JPG veya PNG · En fazla 10 MB</Text>
          </>
        )}
      </View>
      {asset ? <Text style={{ fontSize: 12.5, color: c.mute, textAlign: 'center', marginBottom: 10 }}>{asset.fileName || 'fotoğraf'}{asset.fileSize ? ` · ${(asset.fileSize / 1048576).toFixed(1)} MB` : ''}</Text> : null}

      <View style={{ flexDirection: 'row', gap: 10, marginBottom: 16 }}>
        <Btn style={{ flex: 1 }} title="Kamera" icon="camera-outline" onPress={() => sec('kamera')} />
        <Btn style={{ flex: 1 }} variant="o" title="Galeri" icon="image-outline" onPress={() => sec('galeri')} />
      </View>

      <View style={kart}>
        <Text style={{ fontSize: 14, fontWeight: '700', color: c.ink, marginBottom: 10 }}>İyi bir fotoğraf için</Text>
        {tip('sunny-outline', 'Doğal ışık kullanın', 'Flaş ve filtre kullanmayın.')}
        {tip('scan-outline', 'Net ve yakından çekin', 'Cilt bölgesi kadrajın ortasında olsun.')}
        {tip('resize-outline', 'Ölçeği görünür kılın', 'Yanına bir cetvel yerleştirebilirsiniz.')}
      </View>

      <Check checked={consent} onChange={setConsent} style={{ marginBottom: 20 }}>
        Fotoğrafımın ön değerlendirme amacıyla işlenmesine onay veriyorum. <Text style={{ fontWeight: '700' }}>Aydınlatma metni</Text>
        {'\n\n'}Yüzünüzü veya kimlik bilgilerinizi kadraja almayın.
      </Check>

      <View style={[kart, { marginBottom: 20 }]}>
        <Text style={{ fontSize: 15, fontWeight: '700', color: c.ink, marginBottom: 6 }}>Lezyon Hakkında</Text>
        <Text style={{ fontSize: 12.5, color: c.mute, marginBottom: 12 }}>Aşağıdaki soruları fotoğrafınızla birlikte yanıtlayarak ön değerlendirmenin daha doğru yapılmasına yardımcı olabilirsiniz.</Text>
        <Text style={{ fontSize: 12.5, fontWeight: '600', color: c.ink, marginBottom: 8, lineHeight: 18 }}>
          Lezyonun durumu ve geçmişi nedir? (Kaşıntı, büyüme, ağrı, şekil/renk/yapı değişimi, kanama veya kabarıklık var mı? Vücudunuzun neresinde yer alıyor? Kendinizde veya ailenizde cilt kanseri öyküsü var mı?)
        </Text>
        <TextInput
          value={info}
          onChangeText={setInfo}
          multiline
          textAlignVertical="top"
          placeholder="Bilgileri buraya yazın..."
          placeholderTextColor={c.mute}
          style={{ minHeight: 100, borderWidth: 1, borderColor: c.line, borderRadius: 10, padding: 12, fontSize: 13, color: c.ink, backgroundColor: c.bg }}
        />
      </View>

      <ErrText style={{ textAlign: 'center' }}>{err}</ErrText>
      <Btn title="Değerlendirmeyi gör" onPress={gonder} loading={busy} disabled={!(asset && consent)} />
    </Screen>
  );
}

export function Done({ photo, onAgain }) {
  const c = useTheme();
  return (
    <Screen menu>
      <Brand />
      <View style={{ alignItems: 'center' }}>
        <View style={{ width: 56, height: 56, borderRadius: 28, backgroundColor: c.ok + '29', alignItems: 'center', justifyContent: 'center', marginTop: 8, marginBottom: 14 }}>
          <Ionicons name="checkmark" size={30} color={c.ok} />
        </View>
        <H1>Fotoğrafınız yüklendi</H1>
        <Sub style={{ textAlign: 'center' }}>Demo sürümünde yapay zeka değerlendirmesi henüz yok. Sonraki aşamada fotoğraf sunucuya gönderilecek ve yapay zeka size birkaç soru soracak.</Sub>
        {photo ? <Image source={{ uri: photo.uri }} style={{ width: '100%', height: 260, borderRadius: 14, marginBottom: 16 }} resizeMode="cover" /> : null}
        <Btn title="Yeni fotoğraf ekle" onPress={onAgain} style={{ alignSelf: 'stretch' }} />
        <Note>Bu uygulama tanı koymaz. Kesin değerlendirme için dermatolog muayenesi gerekir.</Note>
      </View>
    </Screen>
  );
}
