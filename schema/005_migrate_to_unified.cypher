// MIGRASI idempoten ke skema terpadu: buang label/relasi/constraint domain lama. Aman dijalankan berulang (no-op bila sudah bersih).
// Setelah ini jalankan ulang loader (python -m scripts.run_ingest) agar graf terbentuk dengan label/relasi generik.
DROP CONSTRAINT unit_id IF EXISTS;
DROP CONSTRAINT unitkerja_name IF EXISTS;
DROP CONSTRAINT uke_id IF EXISTS;
DROP CONSTRAINT instansi_name IF EXISTS;
DROP CONSTRAINT wilayah_name IF EXISTS;
DROP CONSTRAINT bidang_name IF EXISTS;
DROP CONSTRAINT kategori_name IF EXISTS;
DROP CONSTRAINT tahun_value IF EXISTS;
DROP CONSTRAINT jenisfile_name IF EXISTS;
DROP CONSTRAINT jenispgetahuan_name IF EXISTS;
DROP CONSTRAINT jenisoutput_name IF EXISTS;
DROP CONSTRAINT topik_name IF EXISTS;
DROP CONSTRAINT mitra_name IF EXISTS;
DROP CONSTRAINT disaster_type_name IF EXISTS;
DROP CONSTRAINT infrastructure_name IF EXISTS;
DROP CONSTRAINT year_value IF EXISTS;
DROP CONSTRAINT measure_unit_name IF EXISTS;
DROP CONSTRAINT document_file_name IF EXISTS;
DROP INDEX unit_eselon IF EXISTS;
DROP INDEX disaster_event_year IF EXISTS;
DROP INDEX damage_report_year IF EXISTS;
MATCH (n:DisasterEvent) REMOVE n:DisasterEvent;
MATCH (n:DamageReport) REMOVE n:DamageReport;
MATCH ()-[r:PUBLISHED_BY|PRODUCED_BY|UNDER_DIVISION|PART_OF|HAS_PARTNER|USES_REFERENCE|NEXT_CHUNK|CITES|PART_OF_LOCATION|ABOUT_LOCATION|IN_SUB_CATEGORY|COVERS_DISASTER|AFFECTS_INFRASTRUCTURE|FOR_YEAR|MEASURED_IN|BERADA_DALAM_UKE|DITERBITKAN_OLEH|BERKATEGORI|MEMILIKI_SUB_KATEGORI|MENCAKUP_SUBKATEGORI|MENCAKUP_WILAYAH|TAHUN_DATA|TERKAIT_DENGAN]-() DELETE r;
MATCH (n) WHERE any(l IN labels(n) WHERE l IN ['UnitKerja','UKE','UKEInternal','UKEEksternal','DisasterType','Infrastructure','MeasureUnit','Year','Instansi','Wilayah','KategoriData','BidangKategori','Tahun','Satuan','JenisFile','JenisPengetahuan','JenisOutput','Topik','Entitas','Mitra','Regulasi','Regulation']) DETACH DELETE n;
