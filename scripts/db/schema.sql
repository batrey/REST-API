-- UUID Extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- updated_at column trigger
CREATE OR REPLACE FUNCTION set_updated_at_columns()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ language "plpgsql";

create table vehicles (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  vin varchar(17) NOT NULL,
  make varchar,
  model varchar,
  year int,
  notes varchar,
  created_at timestamp with time zone NOT NULL default NOW(),
  updated_at timestamp with time zone NOT NULL default NOW()
);

CREATE UNIQUE INDEX vehicles_vin_idx ON vehicles(vin);

CREATE TRIGGER set_updated_at_vehicles
BEFORE UPDATE ON vehicles
FOR EACH ROW EXECUTE PROCEDURE set_updated_at_columns();
